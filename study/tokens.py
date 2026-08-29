"""Token estimation for the budget knob.

The budget is the study's independent variable, so a raw chars/4 heuristic is
not good enough on its own: the estimator self-calibrates against the ACTUAL
prompt_tokens the provider reports on every response (usage feedback), keeping
an EMA correction factor per run. After the first couple of calls the estimate
tracks the real tokenizer closely; the realized view size is logged either way,
so any residual error is visible in the data rather than hidden.
"""
from __future__ import annotations

CHARS_PER_TOKEN = 4.0


def _msg_chars(m: dict) -> int:
    c = m.get("content") or ""
    if isinstance(c, list):  # multimodal parts
        c = "".join(p.get("text", "") for p in c if isinstance(p, dict))
    n = len(c)
    for tc in m.get("tool_calls") or []:      # native tool-calling: command text
        n += len(str((tc.get("function") or {}).get("arguments") or "")) + 24
    return n + len(m.get("role", "")) + 8     # small per-message overhead


class CalibratedEstimator:
    def __init__(self, chars_per_token: float = CHARS_PER_TOKEN):
        self.cpt = chars_per_token
        self.ratio = 1.0          # actual / naive-estimate, EMA
        self._alpha = 0.5

    def naive(self, messages: list[dict]) -> int:
        return int(sum(_msg_chars(m) for m in messages) / self.cpt)

    def tokens(self, messages: list[dict]) -> int:
        return max(1, int(self.naive(messages) * self.ratio))

    def observe(self, sent_messages: list[dict], actual_prompt_tokens: int) -> None:
        naive = self.naive(sent_messages)
        if naive > 0 and actual_prompt_tokens > 0:
            r = actual_prompt_tokens / naive
            self.ratio = (1 - self._alpha) * self.ratio + self._alpha * r
