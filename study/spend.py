"""Spend governor (§07): per-block gates and a global abort.

Every completed run appends {usd, block, run_id, ts} to a jsonl ledger.
The driver checks gates BEFORE launching each run; passing a gate stops the
campaign, it does not merely warn.
"""
from __future__ import annotations

import json
import os
import threading
import time

from study.config import GLOBAL_ABORT_USD, LEDGER_PATH, SPEND_GATES


class SpendGateExceeded(RuntimeError):
    pass


class Ledger:
    _lock = threading.Lock()

    def __init__(self, path: str = LEDGER_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def add(self, usd: float, block: str, run_id: str) -> None:
        with self._lock, open(self.path, "a") as f:
            f.write(json.dumps({"usd": round(usd, 6), "block": block,
                                "run_id": run_id, "ts": time.time()}) + "\n")

    def total(self) -> float:
        if not os.path.exists(self.path):
            return 0.0
        with open(self.path) as f:
            return sum(json.loads(line)["usd"] for line in f if line.strip())

    def check(self, block: str) -> None:
        spent = self.total()
        if spent >= GLOBAL_ABORT_USD:
            raise SpendGateExceeded(f"GLOBAL abort: ${spent:.2f} >= ${GLOBAL_ABORT_USD}")
        gate = SPEND_GATES.get(block)
        if gate is not None and spent >= gate:
            raise SpendGateExceeded(f"block {block} gate: ${spent:.2f} >= ${gate}")
