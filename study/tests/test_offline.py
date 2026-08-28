"""Offline tests: every strategy, the replay loop, spend gates, metrics. No API."""
from __future__ import annotations

import math

from study.analysis.metrics import all_at_k, cost_of_pass, delta, paired_bootstrap, pass1
from study.strategies import HEAD_N, ViewState, build_view, is_write_msg
from study.summarizer import simulated_summarize
from study.tokens import CalibratedEstimator


def synth_messages(n_turns: int = 40, obs_chars: int = 3000) -> list[dict]:
    msgs = [
        {"role": "system", "content": "You are a coding agent. " * 40},
        {"role": "user", "content": "Fix the bug in parser.py so test_edge passes. " * 20},
    ]
    for i in range(n_turns):
        cmd = f"sed -i 's/old/new{i}/' parser.py" if i % 5 == 0 else f"pytest -x tests/ -k case{i}"
        msgs.append({"role": "assistant", "content": f"Let me try step {i}.\n```bash\n{cmd}\n```"})
        msgs.append({"role": "user", "content": f"<output step={i}>\n" + ("E" * obs_chars)})
    return msgs


def test_full_is_identity():
    est, msgs = CalibratedEstimator(), synth_messages()
    v = build_view(msgs, strategy="FULL", budget_tokens=None, est=est, state=ViewState())
    assert v is msgs


def test_under_budget_untouched():
    est, msgs = CalibratedEstimator(), synth_messages(4, 200)
    v = build_view(msgs, strategy="SUMMARIZE", budget_tokens=10**6, est=est,
                   state=ViewState(), summarize_fn=simulated_summarize())
    assert v is msgs


def _fits(v, est, budget, slack=1.15):
    return est.tokens(v) <= budget * slack  # estimator noise tolerance


def test_prune_respects_budget_and_head():
    est, msgs = CalibratedEstimator(), synth_messages()
    budget = est.tokens(msgs) // 4
    v = build_view(msgs, strategy="PRUNE", budget_tokens=budget, est=est, state=ViewState())
    assert v[:HEAD_N] == msgs[:HEAD_N] and _fits(v, est, budget)
    assert v[-1] == msgs[-1]  # keeps the most recent turn


def test_retrieve_pins_writes_and_recent():
    est, msgs = CalibratedEstimator(), synth_messages()
    budget = est.tokens(msgs) // 3
    v = build_view(msgs, strategy="RETRIEVE", budget_tokens=budget, est=est, state=ViewState())
    assert v[:HEAD_N] == msgs[:HEAD_N] and _fits(v, est, budget)
    assert v[-1] == msgs[-1]                              # recent pinned
    body = msgs[HEAD_N:]
    idx = {id(m): i for i, m in enumerate(body)}
    order = [idx[id(m)] for m in v[HEAD_N:]]
    assert order == sorted(order)                          # chronological
    n_writes_kept = sum(1 for m in v if is_write_msg(m))
    assert n_writes_kept >= 1                              # write turns survive


def test_summarize_compacts_and_notes():
    est, msgs = CalibratedEstimator(), synth_messages()
    budget = est.tokens(msgs) // 4
    st = ViewState()
    v = build_view(msgs, strategy="SUMMARIZE", budget_tokens=budget, est=est, state=st,
                   summarize_fn=simulated_summarize(300))
    assert st.compactions == 1 and st.note is not None
    assert any("[COMPACTED MEMORY]" in str(m.get("content", "")) for m in v)
    assert v[:HEAD_N] == msgs[:HEAD_N] and _fits(v, est, budget)


def test_overflow_guard_fires_on_tiny_budget():
    est = CalibratedEstimator()
    msgs = synth_messages(10, 12000)  # huge observations
    head_t = est.tokens(msgs[:HEAD_N])
    st = ViewState()
    build_view(msgs, strategy="SUMMARIZE", budget_tokens=int(head_t * 2.6), est=est,
               state=st, summarize_fn=simulated_summarize(300))
    assert any(e["event"] == "recent_overflow" for e in st.events)


def test_never_mutates_input():
    est, msgs = CalibratedEstimator(), synth_messages()
    snapshot = [dict(m) for m in msgs]
    for strat in ("PRUNE", "RETRIEVE", "SUMMARIZE"):
        build_view(msgs, strategy=strat, budget_tokens=est.tokens(msgs) // 4, est=est,
                   state=ViewState(), summarize_fn=simulated_summarize())
    assert msgs == snapshot


def test_estimator_calibrates():
    est = CalibratedEstimator()
    msgs = synth_messages(6, 500)
    naive = est.tokens(msgs)
    est.observe(msgs, naive * 2)   # provider says we undercount 2x
    assert abs(est.tokens(msgs) / naive - 1.5) < 0.01  # EMA alpha=0.5 -> ratio 1.5


def test_metrics_and_bootstrap():
    rows_sum, rows_ret = [], []
    for t in range(12):
        for s in range(3):
            # summarize: coin-flippy on half the tasks; retrieve: stable
            rows_sum.append({"task_id": f"t{t}", "reward": int((t + s) % 2 == 0 if t < 6 else t % 3 == 0),
                             "total_cost_usd": 0.5})
            rows_ret.append({"task_id": f"t{t}", "reward": int(t % 3 == 0), "total_cost_usd": 0.6})
    assert 0 <= pass1(rows_sum) <= 1 and 0 <= all_at_k(rows_sum) <= 1
    assert delta(rows_ret) == 0.0                      # stable arm: no gap
    assert delta(rows_sum) > 0.0                       # flippy arm: gap
    assert math.isfinite(cost_of_pass(rows_sum))
    out = paired_bootstrap(rows_sum, rows_ret, delta, n_boot=500)
    assert out["n_tasks"] == 12 and out["point"] > 0


def test_spend_gates(tmp_path):
    from study import spend
    led = spend.Ledger(str(tmp_path / "ledger.jsonl"))
    led.add(5.0, "E0", "r1"); led.check("E0")          # under the $12 gate
    led.add(8.0, "E0", "r2")
    try:
        led.check("E0"); assert False, "gate should have fired"
    except spend.SpendGateExceeded:
        pass
