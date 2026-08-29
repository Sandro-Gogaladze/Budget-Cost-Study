"""Frozen study constants — Context Budget Study (docs/context-budget-study.html).

Anything here that changes mid-study is a dated deviation from the analysis plan.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

def _load_dotenv() -> None:
    """Load KEY=VALUE lines from the project .env (never committed) into os.environ."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_dotenv()

# ---------------------------------------------------------------- identity
SALT = "gaia-2026-08"            # sampling salt (§03) — part of the analysis plan
N_TASKS = 12                     # ORDER[:12]; extend via ORDER[:24] later, never re-draw
K_SEEDS = 3                      # seeds 0..2 now; 3,4 later — nested, like tasks

# ---------------------------------------------------------------- model / proxy
PROXY_BASE_URL = "https://gemini-litellm-proxy-production.up.railway.app/v1"
KEY_ENV = "LITELLM_KEY"          # never write the key to a file

# DECISION (user, 2026-08-29): primary switched to Flash-Lite — L0 preflight
# verified caching (cold $0.00295 -> warm $0.00111), input exactly $0.25/M,
# and NO default thinking. ~6x cheaper; the 3.5 Flash census is retained as
# the stronger-generation FULL-only comparison point.
PRIMARY_MODEL = "gemini/gemini-3.1-flash-lite"
ARCHIVE_MODEL = "gemini/gemini-3.5-flash"          # E1 census done on this (results/)
# litellm needs the openai-compat provider prefix + our proxy base:
def litellm_name(model: str) -> str:
    return f"openai/{model}"

MODEL_PINNED_AT = "2026-08-28"   # date the model string was pinned (canary-check weekly)

# ---------------------------------------------------------------- price table (frozen)
# $ per 1M tokens — MEASURED against the proxy's x-litellm-response-cost on
# 2026-08-28 (preflight): in=$1.50, cached=$0.15 (0.1x), out=$9.00 incl. thinking.
# 5x the original planning guess; E1's forecast uses these.
PRICE_TABLE_DATE = "2026-08-28"
PRICES = {
    "gemini/gemini-3.5-flash":      {"in": 1.50, "cached_in": 0.15, "out": 9.00},
    "gemini/gemini-3.1-flash-lite": {"in": 0.25, "cached_in": 0.025, "out": 1.50},  # in/cached VERIFIED vs billing 2026-08-29
}

# Thinking: default effort burns ~1K reasoning tokens/step at out-price.
# "minimal" zeroes it (verified through the proxy; "low" is silently ignored).
# E1 measures both on seed 0; the study then FIXES one value across every arm.
REASONING_EFFORT = None   # None = provider default; "minimal" = thinking off

# ---------------------------------------------------------------- budgets (§06)
# DECISION (user, 2026-08-28): ABSOLUTE budgets — one token value per level for
# every task, like production. Values are fixed by E2 from E1's measured peak
# distribution (target: TIGHT forces >=3 compactions on >=50% of tasks and >=1 on
# >=75%; LOOSE treats >=30%). Tasks whose peak < budget never compact — that is
# the real production mixture, reported as the treated share per level.
BUDGETS = {"LOOSE": None, "TIGHT": None}           # tokens; set after E2, then frozen
HEAD_FLOOR_MULT = 2.5                              # sanity guard: budget must exceed 2.5x head
KEEP_RECENT = 4                  # verbatim recent turns kept beside the summary note
SUMM_TEMPERATURE = 0.3           # SUMMARIZE arm; SUMMARIZE_T0 uses 0.0

# ---------------------------------------------------------------- guardrails (§07)
# DECISION (user, 2026-08-28): match DeepSWE's own protocol — NO step cap.
# Per-run guards: cost $7 (user, 2026-08-28) and DeepSWE's 9,000s wall clock.
# Truncation rates (cost_limit / timeout) are still reported per arm.
STEP_LIMIT = 0                   # 0 = unlimited (mini skips the check)
COST_LIMIT_USD = 7.0             # sole runaway guard — identical in every arm
WALL_TIME_S = 9000               # DeepSWE's own cap, unchanged

# Cumulative spend gates ($) — the driver refuses to launch past these (§07 table).
SPEND_GATES = {"E0": 12.0, "E1": 45.0, "E5": 155.0, "E6": 180.0}
GLOBAL_ABORT_USD = 180.0

# ---------------------------------------------------------------- paths
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS_DIR = os.path.join(ROOT, "runs")
DEEPSWE_DIR = os.path.join(ROOT, "deep-swe")
LEDGER_PATH = os.path.join(RUNS_DIR, "spend_ledger.jsonl")


@dataclass
class ArmSpec:
    strategy: str                # FULL | PRUNE | SUMMARIZE | SUMMARIZE_T0 | RETRIEVE
    budget_level: str            # NATIVE | LOOSE | TIGHT
    def label(self) -> str:
        return f"{self.strategy}@{self.budget_level}"


# E5 grid (§07): TIGHT block first — it carries the primary contrast.
GRID = [
    ArmSpec("SUMMARIZE", "TIGHT"), ArmSpec("RETRIEVE", "TIGHT"),
    ArmSpec("SUMMARIZE", "LOOSE"), ArmSpec("RETRIEVE", "LOOSE"),
    ArmSpec("FULL", "NATIVE"),
]
