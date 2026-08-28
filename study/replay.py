"""E2 replay calibration (§07): zero API calls.

Sweeps budget fractions against saved FULL trajectories through the SAME
build_view() the live agent uses, reporting compaction pressure per fraction
and a predicted E5 cost from the §08 arithmetic.

Run:  .venv/bin/python -m study.replay runs/E1-*
"""
from __future__ import annotations

import glob
import json
import sys

from study.config import BUDGETS, HEAD_FLOOR_MULT, KEEP_RECENT, PRICES, PRIMARY_MODEL
from study.strategies import HEAD_N, ViewState, build_view
from study.summarizer import simulated_summarize
from study.tokens import CalibratedEstimator

ABS_SWEEP = [16_000, 24_000, 32_000, 48_000, 64_000, 96_000, 128_000, 160_000, 192_000]


def load_traj(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def replay_one(messages: list[dict], budget: int, strategy: str) -> dict:
    est = CalibratedEstimator()
    peak = est.tokens(messages)
    head = est.tokens(messages[:HEAD_N])
    state = ViewState()
    view_tokens = []
    # replay the growing history call-by-call, as the live loop would see it
    for upto in range(HEAD_N + 1, len(messages) + 1):
        v = build_view(messages[:upto], strategy=strategy, budget_tokens=budget,
                       est=est, state=state, keep_recent=KEEP_RECENT,
                       summarize_fn=simulated_summarize())
        view_tokens.append(est.tokens(v))
    overflows = sum(1 for e in state.events if e["event"] == "recent_overflow")
    return {
        "strategy": strategy, "budget": budget, "peak": peak, "head": head,
        "compactions": state.compactions,
        "median_view": sorted(view_tokens)[len(view_tokens) // 2] if view_tokens else 0,
        "overflow_rate": overflows / max(1, len(view_tokens)),
    }


def predicted_cost_usd(view_tokens_per_call: list[int], model: str = PRIMARY_MODEL,
                       cache_hit: float = 0.9, out_per_call: int = 400) -> float:
    """§08 arithmetic: cached prefix at 0.1x, new suffix at 1x."""
    p = PRICES[model]
    usd = 0.0
    prev = 0
    for v in view_tokens_per_call:
        cached = min(prev, v) * cache_hit
        fresh = v - cached
        usd += (cached * p["cached_in"] + fresh * p["in"] + out_per_call * p["out"]) / 1e6
        prev = v
    return usd


def main(run_globs: list[str]) -> None:
    paths = [p for g in run_globs for p in glob.glob(f"{g}/trajectory.json")]
    if not paths:
        print("no trajectories found"); return
    trajs = [load_traj(p) for p in paths]
    print(f"{len(trajs)} trajectories\n")
    print(f"{'budget':>8} {'strategy':<10} {'treated':>8} {'>=3 comp':>9} {'med view/head':>14} {'ovfl':>6}")
    for budget in ABS_SWEEP:
        for strat in ("SUMMARIZE", "PRUNE", "RETRIEVE"):
            rows = [replay_one(t, budget, strat) for t in trajs]
            ge1 = sum(r["compactions"] >= 1 for r in rows) / len(rows)
            ge3 = sum(r["compactions"] >= 3 for r in rows) / len(rows)
            vh = sorted(r["median_view"] / max(1, r["head"]) for r in rows)[len(rows) // 2]
            ov = max(r["overflow_rate"] for r in rows)
            print(f"{budget:>8,} {strat:<10} {ge1:>8.0%} {ge3:>9.0%} {vh:>14.1f} {ov:>6.0%}")
    print("\npick (then freeze in config.BUDGETS):"
          "\n  TIGHT = largest value with >=1 compaction on >=75% of tasks AND >=3 on >=50%"
          "\n  LOOSE = value treating 30-50% of tasks"
          "\nif set, current config is checked below:")
    for level, budget in BUDGETS.items():
        if budget is None:
            print(f"  {level}: not set"); continue
        rows = [replay_one(t, budget, "SUMMARIZE") for t in trajs]
        ge1 = sum(r["compactions"] >= 1 for r in rows) / len(rows)
        ge3 = sum(r["compactions"] >= 3 for r in rows) / len(rows)
        print(f"  {level} ({budget:,}): treated {ge1:.0%} · compact>=3 {ge3:.0%}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["runs/*"])
