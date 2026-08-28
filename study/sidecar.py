"""Sidecar logging (§08): runs.jsonl + steps.jsonl, one line per record.

Usage detail (incl. cached tokens) is mined from the full API response that
mini-swe-agent persists on every assistant message (extra.response.usage) —
that is what turns the cost axis from modelled into measured.
"""
from __future__ import annotations

import json
import os
import time

from study.config import RUNS_DIR


def extract_usage(message: dict) -> dict:
    """Pull usage detail out of a persisted model response, tolerantly."""
    resp = message.get("extra", {}).get("response", {}) or {}
    u = resp.get("usage") or {}
    ptd = u.get("prompt_tokens_details") or {}
    ctd = u.get("completion_tokens_details") or {}
    return {
        "prompt_tokens": u.get("prompt_tokens", 0),
        "completion_tokens": u.get("completion_tokens", 0),
        "cached_tokens": (ptd.get("cached_tokens") or 0),
        "reasoning_tokens": (ctd.get("reasoning_tokens") or 0),
        "cost_usd": message.get("extra", {}).get("cost", 0.0),
    }


class Sidecar:
    def __init__(self, run_id: str, base: str = RUNS_DIR):
        self.run_id = run_id
        self.dir = os.path.join(base, run_id)
        os.makedirs(self.dir, exist_ok=True)
        self._steps = open(os.path.join(self.dir, "steps.jsonl"), "a")

    def step(self, **row) -> None:
        row.update(run_id=self.run_id, ts=time.time())
        self._steps.write(json.dumps(row) + "\n")
        self._steps.flush()

    def finish(self, **row) -> None:
        row.update(run_id=self.run_id, ts=time.time())
        with open(os.path.join(self.dir, "run.json"), "w") as f:
            json.dump(row, f, indent=2)
        self._steps.close()

    def save_trajectory(self, messages: list[dict]) -> None:
        with open(os.path.join(self.dir, "trajectory.json"), "w") as f:
            json.dump(messages, f)
