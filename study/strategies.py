"""Pure view builders (§06) — the entire intervention, usable offline.

build_view() is a pure function over a message list: the agent calls it live,
and replay.py calls it against saved trajectories with a simulated summarizer.
Nothing here mutates the input list.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

HEAD_N = 2  # system + instruction — ALWAYS kept, never compacted

# --------------------------------------------------------------------- state
@dataclass
class ViewState:
    note: Optional[str] = None
    compactions: int = 0
    summarizer_cost_usd: float = 0.0
    events: list = field(default_factory=list)   # e.g. recent_overflow records

    def log(self, kind: str, **kw):
        self.events.append({"event": kind, **kw})


# --------------------------------------------------------------------- utils
def _content(m: dict) -> str:
    c = m.get("content") or ""
    if isinstance(c, list):
        c = "".join(p.get("text", "") for p in c if isinstance(p, dict))
    parts = [c] if isinstance(c, str) else [""]
    for tc in m.get("tool_calls") or []:      # commands live in arguments
        parts.append(str((tc.get("function") or {}).get("arguments") or ""))
    return " ".join(p for p in parts if p)


_WRITE_RE = re.compile(
    r"(>>?\s*[\w./-]+|<<\s*['\"]?\w+|sed\s+-i|\btee\b|git\s+apply|\bpatch\b|applypatch)"
)

def is_write_msg(m: dict) -> bool:
    """Heuristic: does this turn contain a file-write action?"""
    return m.get("role") == "assistant" and bool(_WRITE_RE.search(_content(m)))


def group_turns(body: list[dict]) -> list[list[dict]]:
    """Group into atomic turns: an assistant message plus the tool/user
    observations that answer it. Never split — an orphaned tool response is an
    API error under native tool-calling, and a command without its output is
    meaningless under the text protocol."""
    groups: list[list[dict]] = []
    for m in body:
        if m.get("role") == "assistant" or not groups:
            groups.append([m])
        else:
            groups[-1].append(m)
    return groups


def _flat(groups: list[list[dict]]) -> list[dict]:
    return [m for g in groups for m in g]


def keep_last_that_fit(body: list[dict], room: int, est) -> list[dict]:
    groups = group_turns(body)
    out: list[list[dict]] = []
    for g in reversed(groups):
        if est.tokens(_flat([g] + out)) > room:
            break
        out.insert(0, g)
    return _flat(out)


def keep_last_n(body: list[dict], n: int) -> list[dict]:
    """Last n TURNS (not messages)."""
    return _flat(group_turns(body)[-n:]) if n > 0 else []


# --------------------------------------------------------------------- BM25
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|\d+")

def _terms(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)][:4000]


def bm25_scores(query: str, docs: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    doc_terms = [_terms(d) for d in docs]
    n = len(docs)
    if n == 0:
        return []
    avgdl = sum(len(t) for t in doc_terms) / n or 1.0
    df: dict[str, int] = {}
    for terms in doc_terms:
        for t in set(terms):
            df[t] = df.get(t, 0) + 1
    q = _terms(query)
    scores = []
    for terms in doc_terms:
        tf: dict[str, int] = {}
        for t in terms:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for t in set(q):
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(terms) / avgdl))
        scores.append(s)
    return scores


def subgoal_query(messages: list[dict]) -> str:
    """CURRENT subgoal: the task instruction plus the last two turns (§06)."""
    instruction = _content(messages[1]) if len(messages) > 1 else ""
    recent = " ".join(_content(m) for m in messages[-2:])
    return (instruction + " " + recent)[:8000]


def retrieve_view(messages: list[dict], room: int, est, keep_recent: int) -> list[dict]:
    head, body = messages[:HEAD_N], messages[HEAD_N:]
    groups = group_turns(body)
    pinned = set(range(max(0, len(groups) - keep_recent), len(groups)))
    pinned |= {i for i, g in enumerate(groups) if any(is_write_msg(m) for m in g)}
    q = subgoal_query(messages)
    scores = bm25_scores(q, [" ".join(_content(m) for m in g) for g in groups])
    ranked = sorted(range(len(groups)), key=lambda i: -scores[i])
    chosen: set[int] = set()
    def fits(cand):
        return est.tokens(_flat([groups[j] for j in sorted(cand)])) <= room
    for i in sorted(pinned, reverse=True):
        if fits(chosen | {i}):
            chosen.add(i)
    for i in ranked:
        if i not in chosen and fits(chosen | {i}):
            chosen.add(i)
    return head + _flat([groups[i] for i in sorted(chosen)])  # chronological


# --------------------------------------------------------------------- main
def build_view(
    messages: list[dict],
    *,
    strategy: str,
    budget_tokens: Optional[int],
    est,
    state: ViewState,
    keep_recent: int = 4,
    summarize_fn: Optional[Callable] = None,   # (older_msgs, prior_note, temperature) -> (text, usd)
    summ_temperature: float = 0.3,
) -> list[dict]:
    if strategy == "FULL" or budget_tokens is None:
        return messages
    if est.tokens(messages) <= budget_tokens:
        return messages                                    # under budget: nothing to do

    head, body = messages[:HEAD_N], messages[HEAD_N:]
    room = budget_tokens - est.tokens(head)
    if room <= 0:
        state.log("head_exceeds_budget", budget=budget_tokens)
        return messages  # degenerate; recorded, never silently truncated to nothing

    if strategy == "PRUNE":
        return head + keep_last_that_fit(body, room, est)

    if strategy == "RETRIEVE":
        return retrieve_view(messages, room, est, keep_recent)

    if strategy in ("SUMMARIZE", "SUMMARIZE_T0"):
        recent = keep_last_n(body, keep_recent)
        older = body[: len(body) - len(recent)]
        t = 0.0 if strategy == "SUMMARIZE_T0" else summ_temperature
        note_text, usd = summarize_fn(older, state.note, t)
        state.note = note_text
        state.summarizer_cost_usd += usd
        state.compactions += 1
        note = {"role": "user", "content": f"[COMPACTED MEMORY]\n{note_text}"}
        view = head + [note] + recent
        if est.tokens(view) > budget_tokens:
            # recent turns alone can exceed a tight budget — shrink, then record it
            dropped = 0
            rgroups = group_turns(recent)
            while len(rgroups) > 1 and est.tokens(head + [note] + _flat(rgroups)) > budget_tokens:
                rgroups = rgroups[1:]
                dropped += 1
            recent = _flat(rgroups)
            state.log("recent_overflow", dropped=dropped)
            view = head + [note] + recent
        return view

    raise ValueError(f"unknown strategy {strategy!r}")
