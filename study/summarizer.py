"""The summarizer: slot-structured compaction notes (§06).

SLOT_PROMPT uses named fields, not free prose, so the note reliably carries
the fact types that matter (constraints, identifiers, open errors, file state,
decisions). The same callable serves the live agent and the E6 t=0
determinism measurement. In replay, use simulated_summarize instead — no API.
"""
from __future__ import annotations

import os

from study.config import KEY_ENV, PRICES, PROXY_BASE_URL, PRIMARY_MODEL, litellm_name

SLOT_PROMPT = """You are compacting an AI coding agent's working history so it can continue \
with less context. Produce a COMPACTED MEMORY note with exactly these sections:

## TASK STATE
What the agent is trying to do and how far it has got.
## CONSTRAINTS
Every requirement, restriction or instruction that must still be honored. Verbatim where possible.
## IDENTIFIERS
Exact file paths, function/class names, ids, version numbers, numeric values encountered.
## FILES CHANGED
Each file the agent created or modified, and how.
## OPEN ERRORS
Failing tests or commands, with the exact error text, and what has been tried.
## DECISIONS
Choices already made and why, so they are not re-litigated.

Be complete but terse. NEVER invent facts. If a prior note is given, merge it: \
carry forward everything still relevant.

"""


def _serialize(older: list[dict], prior_note: str | None) -> str:
    parts = []
    if prior_note:
        parts.append(f"[PRIOR NOTE]\n{prior_note}\n")
    for m in older:
        c = m.get("content", "")
        if isinstance(c, list):
            c = "".join(p.get("text", "") for p in c if isinstance(p, dict))
        parts.append(f"[{m.get('role','?')}]\n{c}")
    return "\n\n".join(parts)


def make_summarizer(model: str = PRIMARY_MODEL):
    """Returns (older, prior_note, temperature) -> (note_text, usd)."""
    import litellm

    def summarize(older: list[dict], prior_note: str | None, temperature: float):
        payload = SLOT_PROMPT + _serialize(older, prior_note)
        resp = litellm.completion(
            model=litellm_name(model),
            api_key=os.environ[KEY_ENV],
            api_base=PROXY_BASE_URL,
            messages=[{"role": "user", "content": payload}],
            temperature=temperature,
            max_tokens=2048,
        )
        u = resp.usage
        p = PRICES[model]
        usd = (u.prompt_tokens * p["in"] + u.completion_tokens * p["out"]) / 1e6
        return resp.choices[0].message.content or "", usd

    return summarize


def simulated_summarize(note_tokens: int = 900):
    """Replay-mode summarizer: emits a placeholder note of realistic size, $0."""
    def summarize(older, prior_note, temperature):
        return "x " * note_tokens, 0.0
    return summarize
