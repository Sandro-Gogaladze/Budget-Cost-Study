"""Deterministic nested task sampling (§03).

ORDER is a fixed pseudo-random ordering of all task ids; every study subset is a
prefix, so later extensions (ORDER[:24], ORDER[:48]) pool cleanly with runs
already paid for. Never re-draw: re-rolling to dodge expensive tasks is length
filtering through the back door.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from study.config import DEEPSWE_DIR, N_TASKS, SALT


def study_order(task_ids: list[str], salt: str = SALT) -> list[str]:
    return sorted(task_ids, key=lambda t: hashlib.sha256((salt + t).encode()).hexdigest())


def all_task_ids(deepswe_dir: str = DEEPSWE_DIR) -> list[str]:
    tasks = Path(deepswe_dir) / "tasks"
    if not tasks.is_dir():
        raise FileNotFoundError(f"clone deep-swe first: {tasks}")
    return sorted(p.name for p in tasks.iterdir() if p.is_dir() and (p / "task.toml").exists())


def study_sample(n: int = N_TASKS) -> list[str]:
    return study_order(all_task_ids())[:n]


def main() -> None:
    order = study_order(all_task_ids())
    sample = order[:N_TASKS]
    out = {"salt": SALT, "n": N_TASKS, "sample": sample, "order": order}
    path = os.path.join(os.path.dirname(__file__), "sample.lock.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {path}")
    for i, t in enumerate(sample):
        print(f"{i:2d}  {t}")


if __name__ == "__main__":
    main()
