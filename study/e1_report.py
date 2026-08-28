"""E1 post-processing: length distribution, measured costs, peaks/heads for the
grid, and the n x K allocation check (§07 E1 gate).

Usage:  .venv/bin/python -m study.e1_report
"""
from __future__ import annotations

import glob
import json
import os
import statistics as st

from study import config as C


def load_runs(pattern: str = "E1-*") -> list[dict]:
    rows = []
    for d in sorted(glob.glob(os.path.join(C.RUNS_DIR, pattern))):
        if not os.path.isdir(d):
            continue
        try:
            run = json.load(open(os.path.join(d, "run.json")))
            steps = [json.loads(l) for l in open(os.path.join(d, "steps.jsonl")) if l.strip()]
            run["_dir"], run["_steps"] = d, steps
            rows.append(run)
        except OSError:
            continue
    # keep the latest run per (task, strategy, seed)
    latest = {}
    for r in rows:
        latest[(r["task_id"], r["strategy"], r["seed"], r["model_id"])] = r
    return list(latest.values())


def main() -> None:
    rows = load_runs()
    if not rows:
        print("no E1 runs found"); return
    peaks, heads = {}, {}
    print(f"{'task':<44} {'steps':>5} {'peak view':>9} {'cached%':>8} {'reason%':>8} {'$':>7}  exit")
    for r in sorted(rows, key=lambda r: r["task_id"]):
        steps = r["_steps"]
        peak = max((s.get("view_tokens", 0) for s in steps), default=0)
        head = steps[0].get("view_tokens", 0) if steps else 0
        pt = sum(s.get("prompt_tokens", 0) for s in steps) or 1
        ct = sum(s.get("completion_tokens", 0) for s in steps) or 1
        cached = sum(s.get("cached_tokens", 0) for s in steps)
        reas = sum(s.get("reasoning_tokens", 0) for s in steps)
        if r["strategy"] == "FULL" and r["model_id"] == C.PRIMARY_MODEL:
            peaks[r["task_id"]], heads[r["task_id"]] = peak, head
        print(f"{r['task_id']:<44} {r['steps']:>5} {peak:>9,} {cached/pt:>8.0%} "
              f"{reas/ct:>8.0%} {r['total_cost_usd']:>7.3f}  {r['exit_reason']}")

    costs = [r["total_cost_usd"] for r in rows if r["model_id"] == C.PRIMARY_MODEL]
    pk = sorted(peaks.values())
    if pk:
        q = lambda f: pk[min(len(pk) - 1, int(f * len(pk)))]
        print(f"\npeak view tokens: p10={q(.1):,} p25={q(.25):,} p50={q(.5):,} "
              f"p75={q(.75):,} p90={q(.9):,}")
    if costs:
        mean_c = st.mean(costs)
        print(f"cost/run: mean=${mean_c:.3f} median=${st.median(costs):.3f} max=${max(costs):.3f}")
        grid_budget = 104.0
        afford = grid_budget / max(mean_c * 0.7, 1e-9)   # treatment runs ~0.7x FULL
        print(f"E5 allocation: ~{afford:.0f} treatment runs affordable "
              f"-> n*K per (strategy,budget) = {afford/4:.0f}   (need {C.N_TASKS}*{C.K_SEEDS}={C.N_TASKS*C.K_SEEDS})")
    step_counts = sorted(r["steps"] for r in rows)
    if step_counts:
        p90 = step_counts[min(len(step_counts) - 1, int(0.9 * len(step_counts)))]
        print(f"steps: median={st.median(step_counts):.0f} p90={p90} "
              f"(informational — study runs uncapped per user decision)")

    json.dump(peaks, open(os.path.join(C.RUNS_DIR, "peaks.json"), "w"), indent=2)
    json.dump(heads, open(os.path.join(C.RUNS_DIR, "heads.json"), "w"), indent=2)
    print(f"\nwrote runs/peaks.json + runs/heads.json ({len(peaks)} tasks)")


if __name__ == "__main__":
    main()
