"""E7 re-pricing (§07): four billing regimes over already-logged steps. $0.

observed  — the real bill (cached tokens as reported)
no_cache  — every prompt token at full input price
cold      — a user who returns after cache TTL: first call of each run full price,
            later calls cached as observed
batch     — observed minus 50% (hypothetical batch discount)
"""
from __future__ import annotations

import glob
import json
import sys

from study.config import PRICES, PRIMARY_MODEL


def load_steps(run_dir: str) -> list[dict]:
    out = []
    try:
        with open(f"{run_dir}/steps.jsonl") as f:
            out = [json.loads(l) for l in f if l.strip()]
    except OSError:
        pass
    return out


def price(steps: list[dict], regime: str, model: str = PRIMARY_MODEL) -> float:
    p = PRICES[model]
    usd = 0.0
    for i, s in enumerate(steps):
        pt, ct = s.get("prompt_tokens", 0), s.get("completion_tokens", 0)
        cached = s.get("cached_tokens", 0)
        if regime == "no_cache":
            cached = 0
        if regime == "cold" and i == 0:
            cached = 0
        usd += ((pt - cached) * p["in"] + cached * p["cached_in"] + ct * p["out"]) / 1e6
    if regime == "batch":
        usd *= 0.5
    return usd


def main(globs: list[str]) -> None:
    dirs = [d for g in globs for d in glob.glob(g)]
    for regime in ("observed", "no_cache", "cold", "batch"):
        total = sum(price(load_steps(d), regime) for d in dirs)
        print(f"{regime:>9}: ${total:.4f} over {len(dirs)} runs")


if __name__ == "__main__":
    main(sys.argv[1:] or ["runs/*"])
