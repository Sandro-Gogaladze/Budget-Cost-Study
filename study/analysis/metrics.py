"""§09 analysis: pass1, all@k, the Delta gap, cost-of-pass, paired bootstrap.

Everything is paired within task; the bootstrap resamples TASKS (the unit of
generalization), 10,000 draws. H1 is reported as an estimate with a CI —
never as a hypothesis test at this N.
"""
from __future__ import annotations

import random
from collections import defaultdict


def by_task(rows: list[dict]) -> dict[str, list[dict]]:
    d = defaultdict(list)
    for r in rows:
        d[r["task_id"]].append(r)
    return dict(d)


def pass1(rows: list[dict]) -> float:
    return sum(r["reward"] for r in rows) / len(rows) if rows else 0.0


def all_at_k(rows: list[dict]) -> float:
    tasks = by_task(rows)
    return sum(all(r["reward"] for r in v) for v in tasks.values()) / len(tasks) if tasks else 0.0


def delta(rows: list[dict]) -> float:
    """pass1 - all@k: the inconsistency (H1 endpoint)."""
    return pass1(rows) - all_at_k(rows)


def cost_of_pass(rows: list[dict]) -> float:
    p = pass1(rows)
    mean_cost = sum(r["total_cost_usd"] for r in rows) / len(rows) if rows else 0.0
    return mean_cost / p if p > 0 else float("inf")


def paired_bootstrap(rows_a: list[dict], rows_b: list[dict], stat, n_boot: int = 10_000,
                     seed: int = 0) -> dict:
    """CI for stat(A) - stat(B), resampling tasks jointly."""
    ta, tb = by_task(rows_a), by_task(rows_b)
    tasks = sorted(set(ta) & set(tb))
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        pick = [tasks[rng.randrange(len(tasks))] for _ in tasks]
        diffs.append(stat([r for t in pick for r in ta[t]]) - stat([r for t in pick for r in tb[t]]))
    diffs.sort()
    point = stat(rows_a) - stat(rows_b)
    return {"point": point,
            "ci95": (diffs[int(0.025 * n_boot)], diffs[int(0.975 * n_boot)]),
            "n_tasks": len(tasks)}
