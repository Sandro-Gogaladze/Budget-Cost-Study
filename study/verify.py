"""Score a run against the task's own verifier (the Harbor flow, standalone).

  1. build tests/Dockerfile (FROM the same pinned image, hidden tests baked in)
  2. mount <run_dir>/logs with the collected model.patch at logs/artifacts/
  3. run test.sh -> writes logs/verifier/reward.json (reward + native partial)

Usage:  .venv/bin/python -m study.verify runs/<run_id> [...]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from study.config import DEEPSWE_DIR


def verify_run(run_dir: str) -> dict:
    run = json.load(open(Path(run_dir) / "run.json"))
    task_id = run["task_id"]
    patch = Path(run_dir) / "model.patch"
    logs = Path(run_dir) / "logs"
    (logs / "artifacts").mkdir(parents=True, exist_ok=True)
    if patch.exists():
        shutil.copy(patch, logs / "artifacts" / "model.patch")
    else:
        (logs / "artifacts" / "model.patch").write_text("")   # empty diff -> reward 0

    tests_dir = Path(DEEPSWE_DIR) / "tasks" / task_id / "tests"
    tag = f"deepswe-verify/{task_id.lower()}"
    subprocess.run(["docker", "build", "-q", "-t", tag, str(tests_dir)],
                   check=True, capture_output=True, text=True)
    subprocess.run(
        ["docker", "run", "--rm", "--network", "none",
         "-v", f"{logs.resolve()}:/logs", tag, "bash", "/tests/test.sh"],
        capture_output=True, text=True, timeout=1800,
    )
    reward_json = logs / "verifier" / "reward.json"
    reward_txt = logs / "verifier" / "reward.txt"
    if reward_json.exists():
        out = json.load(open(reward_json))
    elif reward_txt.exists():
        out = {"reward": float(reward_txt.read_text().strip())}
    else:
        out = {"reward": -1, "error": "no reward produced"}
    # merge score back into run.json
    run["reward"] = out.get("reward", 0)
    run["partial"] = out.get("partial")
    json.dump(run, open(Path(run_dir) / "run.json", "w"), indent=2)
    return out


if __name__ == "__main__":
    for d in sys.argv[1:]:
        print(d, "->", json.dumps(verify_run(d)))
