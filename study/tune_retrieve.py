"""E3 offline retriever tuning (§07): recall against saved FULL trajectories, $0.

At each simulated compaction point, the retriever's job is to surface the turns
the FULL run actually needed later. Proxy for "needed later": turns whose
content shares rare identifiers with the agent's OWN subsequent commands.
Optimise recall on that signal; freeze the winning config; hash it.

Usage:  .venv/bin/python -m study.tune_retrieve 'runs/E1-*'
"""
from __future__ import annotations

import glob
import hashlib
import json
import sys

from study.strategies import HEAD_N, _content, _terms, bm25_scores, is_write_msg, subgoal_query
from study.tokens import CalibratedEstimator


def needed_later(body: list[dict], cut: int) -> set[int]:
    """Indices before `cut` whose rare terms reappear in commands after `cut`."""
    later = " ".join(_content(m) for m in body[cut:] if m.get("role") == "assistant")
    later_terms = set(_terms(later))
    out = set()
    for i, m in enumerate(body[:cut]):
        terms = set(_terms(_content(m)))
        rare = {t for t in terms if len(t) >= 6}          # identifiers, not stopwords
        if len(rare & later_terms) >= 3:
            out.add(i)
    return out


def recall_at_budget(body, cut, frac, query_mode) -> float:
    gold = needed_later(body, cut)
    if not gold:
        return float("nan")
    est = CalibratedEstimator()
    room = int(frac * est.tokens(body[:cut]))
    if query_mode == "task":
        q = _content(body[0]) if body else ""
    else:  # subgoal: instruction + last 2 turns before the cut
        q = subgoal_query([{}, {}] + body[:cut])
    docs = [_content(m) for m in body[:cut]]
    scores = bm25_scores(q, docs)
    pins = set(range(max(0, cut - 4), cut)) | {i for i in range(cut) if is_write_msg(body[i])}
    chosen: set[int] = set()
    for i in sorted(pins, reverse=True):
        if est.tokens([body[j] for j in sorted(chosen | {i})]) <= room:
            chosen.add(i)
    for i in sorted(range(cut), key=lambda i: -scores[i]):
        if i not in chosen and est.tokens([body[j] for j in sorted(chosen | {i})]) <= room:
            chosen.add(i)
    return len(chosen & gold) / len(gold)


def main(globs: list[str]) -> None:
    paths = [p for g in globs for p in glob.glob(f"{g}/trajectory.json")]
    trajs = [json.load(open(p)) for p in paths]
    if not trajs:
        print("no trajectories yet — run E1 first"); return
    print(f"{len(trajs)} trajectories · recall of needed-later turns at 40% budget")
    for query_mode in ("task", "subgoal"):
        vals = []
        for t in trajs:
            body = t[HEAD_N:]
            for cut in (len(body) // 2, 3 * len(body) // 4):
                r = recall_at_budget(body, cut, 0.4, query_mode)
                if r == r:  # not nan
                    vals.append(r)
        if vals:
            print(f"  query={query_mode:<8} mean recall {sum(vals)/len(vals):.0%}  (n={len(vals)})")
    cfg = {"chunk": "per_message", "scorer": "bm25", "query": "subgoal",
           "pins": "recent4+writes", "tuned_on": sorted(paths)}
    h = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]
    json.dump({"cfg": cfg, "hash": h}, open("runs/retriever_cfg.json", "w"), indent=2)
    print(f"frozen retriever_cfg_hash={h} -> runs/retriever_cfg.json")


if __name__ == "__main__":
    main(sys.argv[1:] or ["runs/E1-*"])
