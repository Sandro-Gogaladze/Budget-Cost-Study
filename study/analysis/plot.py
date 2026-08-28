"""The one plot (§09): success · consistency · inverted cost-of-pass vs budget.

Reads runs/*/run.json (after verify.py has merged rewards). Produces
runs/figure.svg with matplotlib if available, else prints the table.

Usage:  .venv/bin/python -m study.analysis.plot
"""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict

from study import config as C
from study.analysis.metrics import all_at_k, cost_of_pass, pass1

LEVELS = ["TIGHT", "LOOSE", "NATIVE"]          # tight -> loose, left to right


def load() -> dict:
    cells = defaultdict(list)
    for d in glob.glob(os.path.join(C.RUNS_DIR, "E*-*")):
        try:
            r = json.load(open(os.path.join(d, "run.json")))
        except OSError:
            continue
        if "reward" not in r:
            continue
        level = ("NATIVE" if r.get("budget_tokens") is None else
                 min(C.BUDGET_FRACS, key=lambda L: abs(
                     C.BUDGET_FRACS[L] * (r.get("peak_full_tokens") or 1) - r["budget_tokens"])))
        strat = "FULL/RETRIEVE-ref" if r["strategy"] == "FULL" else r["strategy"]
        cells[(strat, level)].append(
            {"task_id": r["task_id"], "reward": int(r["reward"] == 1),
             "total_cost_usd": r["total_cost_usd"]})
    return cells


def main() -> None:
    cells = load()
    if not cells:
        print("no scored runs yet (run study.verify first)"); return
    print(f"{'strategy':<18} {'level':<7} {'n':>3} {'pass1':>6} {'all@k':>6} {'Δ':>6} {'cop $':>8}")
    series = defaultdict(dict)
    for (strat, level), rows in sorted(cells.items()):
        p1, ak = pass1(rows), all_at_k(rows)
        cop = cost_of_pass(rows)
        series[strat][level] = (p1, ak, cop)
        print(f"{strat:<18} {level:<7} {len(rows):>3} {p1:>6.2f} {ak:>6.2f} {p1-ak:>6.2f} "
              f"{'inf' if cop == float('inf') else f'{cop:8.2f}'}")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for strat, by_level in series.items():
            xs = [i for i, L in enumerate(LEVELS) if L in by_level]
            ax.plot(xs, [by_level[LEVELS[i]][0] for i in xs], "o-", label=f"{strat} pass1")
            ax.plot(xs, [by_level[LEVELS[i]][1] for i in xs], "s--", alpha=.6, label=f"{strat} all@k")
        ax.set_xticks(range(len(LEVELS)), LEVELS)
        ax.set_xlabel("context budget — tighter → looser")
        ax.set_ylabel("rate")
        ax.legend(fontsize=7)
        out = os.path.join(C.RUNS_DIR, "figure.svg")
        fig.savefig(out, bbox_inches="tight")
        print("wrote", out)
    except ImportError:
        print("(matplotlib not installed — table only)")


if __name__ == "__main__":
    main()
