"""Live view of the newest run: step stats + the agent's latest action/observation.

Usage:  .venv/bin/python -m study.watch          # follows the newest runs/ dir
"""
from __future__ import annotations

import glob
import json
import os
import time

from study.config import RUNS_DIR


def newest_run() -> str | None:
    dirs = [d for d in glob.glob(os.path.join(RUNS_DIR, "E*-*")) if os.path.isdir(d)]
    return max(dirs, key=os.path.getmtime) if dirs else None


def last_action(traj_path: str) -> tuple[str, str]:
    try:
        msgs = json.load(open(traj_path)).get("messages") or json.load(open(traj_path))
    except Exception:
        return "", ""
    if isinstance(msgs, dict):
        msgs = msgs.get("messages", [])
    act = obs = ""
    for m in msgs:
        c = m.get("content", "")
        if isinstance(c, list):
            c = "".join(p.get("text", "") for p in c if isinstance(p, dict))
        if m.get("role") == "assistant":
            act, obs = c, ""
        elif m.get("role") == "user" and act:
            obs = c
    return act, obs


def main() -> None:
    seen = 0
    run = None
    while True:
        r = newest_run()
        if r != run:
            run, seen = r, 0
            print(f"\n=== watching {os.path.basename(r or '?')} ===")
        if run:
            steps_path = os.path.join(run, "steps.jsonl")
            if os.path.exists(steps_path):
                rows = [json.loads(l) for l in open(steps_path) if l.strip()]
                for s in rows[seen:]:
                    print(f"s{s['step_idx']:>3}  view {s['view_tokens']:>7,}  "
                          f"cached {s['cached_tokens']:>7,}  ${s['cost_usd']:.4f}  "
                          f"compactions {s.get('compactions', 0)}")
                if len(rows) > seen:
                    act, obs = last_action(os.path.join(run, "live_trajectory.json"))
                    if act:
                        print(f"  ── latest action ──\n  {act.strip()[:500]}")
                    if obs:
                        print(f"  ── observation (trunc) ──\n  {obs.strip()[:300]}")
                seen = len(rows)
            if os.path.exists(os.path.join(run, "run.json")):
                r_ = json.load(open(os.path.join(run, "run.json")))
                print(f"=== finished: {r_.get('exit_reason')} · ${r_.get('total_cost_usd')} ===")
                return
        time.sleep(10)


if __name__ == "__main__":
    main()
