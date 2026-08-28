"""E6 companion: the t=0 identity measurement (§07). ~100 summarizer calls, pennies.

Takes 5 real pre-compaction payloads from saved trajectories, calls the
summarizer 20x each at temperature 0, and reports the exact-match rate — the
number the paper prints instead of claiming "deterministic".

Usage:  .venv/bin/python -m study.t0_check 'runs/E1-*'
"""
from __future__ import annotations

import glob
import hashlib
import json
import sys

from study.strategies import HEAD_N
from study.summarizer import make_summarizer


def main(globs: list[str]) -> None:
    paths = [p for g in globs for p in glob.glob(f"{g}/trajectory.json")][:5]
    if not paths:
        print("no trajectories yet"); return
    summ = make_summarizer()
    total_same = total = 0
    for p in paths:
        msgs = json.load(open(p))
        body = msgs[HEAD_N:]
        older = body[: max(1, len(body) - 4)]
        digests = []
        for _ in range(20):
            note, _usd = summ(older, None, 0.0)
            digests.append(hashlib.sha256(note.encode()).hexdigest())
        same = max(digests.count(d) for d in set(digests))
        total_same += same; total += len(digests)
        print(f"{p.split('/')[-2]}: modal output {same}/20 identical")
    print(f"\nt=0 exact-match rate: {total_same/total:.0%} "
          f"-> paper wording: {'deterministic' if total_same == total else 'reduced-stochasticity'}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["runs/E1-*"])
