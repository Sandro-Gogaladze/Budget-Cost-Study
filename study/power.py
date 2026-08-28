"""E4 power simulation (§07): what can n tasks x K seeds resolve? Pure simulation, $0.

PAIRED design, like the real study: both arms share the same task difficulties.
RETRIEVE resolves each task at its difficulty d. SUMMARIZE resolves the SAME
task at p = d + lam*(0.5 - d): shrunk toward a coin flip (lam = instability
effect size), which raises Delta = pass1 - all@k while moving the mean little.
The task mix is the unfiltered DeepSWE-ish mixture (many hopeless tasks).

Run:  .venv/bin/python -m study.power
"""
from __future__ import annotations

import random

from study.analysis.metrics import delta, paired_bootstrap, pass1


def draw_difficulties(rng, n):
    """Unfiltered task mix at a ~37% model: some hopeless, some easy, some middling."""
    out = []
    for _ in range(n):
        r = rng.random()
        if r < 0.40:      d = 0.0                       # never solved at this model
        elif r < 0.60:    d = rng.uniform(0.05, 0.35)
        elif r < 0.90:    d = rng.uniform(0.35, 0.85)
        else:             d = rng.uniform(0.85, 1.0)
        out.append(d)
    return out


def simulate(n_tasks, k, lam, n_sims=300, seed=0, treated_share=1.0):
    rng = random.Random(seed)
    hits, mean_gaps = 0, []
    for s in range(n_sims):
        d = draw_difficulties(rng, n_tasks)
        # stable arm: same tasks, resolved more deterministically (pushed from 0.5)
        p_ret = [0.5 + (1 if di >= 0.5 else -1) * 0.5 * (abs(di - 0.5) * 2) ** 0.4
                 if di > 0 else 0.0 for di in d]
        # absolute budgets: short tasks never compact -> arms identical there
        treated = [rng.random() < treated_share for _ in range(n_tasks)]
        p_sum = [di + lam * (0.5 - di) if (di > 0 and treated[i]) else p_ret[i]
                 for i, di in enumerate(d)]  # flippier only where compaction fires
        rows_r = [{"task_id": f"t{t}", "reward": int(rng.random() < p_ret[t]), "total_cost_usd": 0}
                  for t in range(n_tasks) for _ in range(k)]
        rows_s = [{"task_id": f"t{t}", "reward": int(rng.random() < p_sum[t]), "total_cost_usd": 0}
                  for t in range(n_tasks) for _ in range(k)]
        out = paired_bootstrap(rows_s, rows_r, delta, n_boot=600, seed=s)
        if out["ci95"][0] > 0:
            hits += 1
        mean_gaps.append(pass1(rows_s) - pass1(rows_r))
    return hits / n_sims, sum(mean_gaps) / len(mean_gaps)


def main():
    print("power for the Delta-gap CI to exclude 0 (paired, unfiltered mix)")
    print(f"{'lam':>4} {'n':>4} {'K':>3} {'power':>7} {'mean shift':>11}")
    for ts in (1.0, 0.75):
        print(f"-- treated share {ts:.0%} --")
        for lam in (0.3, 0.5, 0.7):
            for n in (12, 24):
                for k in (3, 5):
                    pw, ms = simulate(n, k, lam, treated_share=ts)
                    print(f"{lam:>4} {n:>4} {k:>3} {pw:>7.0%} {ms:>+11.3f}")


if __name__ == "__main__":
    main()
