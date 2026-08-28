# Budget-Cost-Study

**What does the context budget cost a long-running coding agent?**

Every deployed agent (Claude Code, Codex, LangChain agents…) sets a token
budget and *compacts* its history — usually by summarizing — when the history
exceeds it. That budget is a real engineering knob that every production system
sets **by guessing**. The industry already believes "max context isn't best"
(Codex reportedly caps ~300K of a 1M window; Claude Code compacts well below
its limit), but nobody has measured where the good range is.

**We measure it.** We sweep the budget from loose to tight on real, long,
auto-graded coding tasks and measure three things:

| Axis | Question | Metric |
|---|---|---|
| **Success** | does tightening the budget lower the solve rate? | benchmark verifier reward (+ graded partial score) |
| **Reliability** | does the agent get *less consistent* run-to-run? | `Δ = pass¹ − all@k` (the inconsistency gap) |
| **Cost** | where are dollars-per-**correct**-answer minimised? | cost-of-pass, cache-adjusted |

We do **not** build a better summarizer. The measurement is the contribution —
the sweep answers "isn't your threshold artificial?" by making the threshold
the object of study.

## The two hypotheses (falsifiable, filed before the confirmatory runs)

- **H1 · Reliability** — as the budget tightens, summarizing keeps a *similar
  average* success to retrieval but becomes far less consistent run-to-run:
  Δ(SUMMARIZE) > Δ(RETRIEVE) at the tight budget while the means overlap.
- **H2 · Cost** — raw dollars fall monotonically as the budget tightens
  (caching arithmetic, see below) but accuracy falls too, so **cost-of-pass is
  U-shaped with an interior minimum**. The location of that minimum is the
  *economically optimal context budget* — the headline number an engineer can
  act on tomorrow. Falsified if monotone, which would itself be the practical
  answer ("always compact" / "never compact").

## Setup

- **Benchmark:** [DeepSWE](https://github.com/datacurve-ai/deep-swe) (Datacurve)
  — 113 original, contamination-free coding tasks across 91 repos and 5
  languages, graded by hand-written program verifiers (independently audited at
  **1.4%** judge disagreement vs 32.4% for SWE-Bench Pro).
- **Agent:** [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)
  (text-based model class — no tool schema, which matters: tool schemas defeat
  Gemini implicit caching). One method is overridden: `query()` builds a
  *derived view* of the message log; the full uncompacted trajectory is always
  preserved.
- **Model:** Gemini 3.5 Flash via an OpenAI-compatible LiteLLM proxy. Chosen
  over cheaper models because its ~37% DeepSWE baseline sits near the maximum
  of p(1−p) — the easiest place to detect a consistency effect.
- **Strategies (arms):** `FULL` (control, true uncompacted on a 1M window) ·
  `PRUNE` · `SUMMARIZE` (the suspect) · `SUMMARIZE_T0` (t=0 control) ·
  `RETRIEVE` (the comparator: subgoal query, BM25, pinned writes).
- **Budgets:** set **per task** as a fraction of that task's own measured peak
  context (LOOSE 60% · TIGHT 20%, floored at 2.5× the head) — so a random
  sample with 5× length variation still receives equal compaction pressure.
- **Sample:** 12 tasks drawn by a salted deterministic ordering of all 113 —
  **random, unfiltered, and nested** (a larger future sample is a strict
  superset; extending the study never invalidates a paid run). Filtering tasks
  on baseline pass rate was explicitly rejected: it selects on the outcome
  using control-arm runs and biases the exact contrast H1 is about.

## Why cost is the strongest axis here

Gemini's implicit caching re-serves an unchanged prefix at ~10% of the input
price, and an agent re-sends nearly its whole history every step:

```
cost(call t) ≈ 0.1p·L(t−1) + p·d_t + p_out·out_t
compaction voids the cache → next call repays full price on the new view V
break-even: m* = 10V/(L−V) ≈ 2–11 calls   (single-digit at tight budgets)
```

So compaction *does* cut raw dollars — monotonically. Raw cost is the boring
quantity; **cost-of-pass** (dollars ÷ P(correct)) is the interesting one, and
its minimum is measurable because cost is measured exactly (provider cache
counters), leaving pass¹ as the only noisy term. Measured on a real 120-step
run: **89% cache-hit rate** (3.79M of 4.26M prompt tokens cached).

## Measured facts this study stands on (2026-08-28)

- Implicit caching **survives the proxy** and its billing honors the discount
  (cold $0.0178 vs warm $0.0068 on an identical call).
- Proxy prices, solved from billed costs: **in $1.50/M · cached $0.15/M ·
  out $9.00/M** (thinking bills as output; ~25× the visible text at default
  effort; `reasoning_effort:"minimal"` zeroes it, `"low"` is ignored).
- Power (paired simulation, unfiltered mix): 12 tasks × K=3 → **~21–29%** on
  the Δ-gap ⇒ H1 is reported as a **pilot estimate with a CI**, never as a
  hypothesis test; confirmation needs ~24×5. Adding tasks beats adding seeds.

## Repo map

```
docs/context-budget-study.html   THE PLAN — single source of truth (open in a browser)
docs/METHODOLOGY.md              the design rationale, metric definitions, gates
docs/DECISIONS.md                dated frozen decisions (deviations must be dated too)
study/                           implementation (see study/README.md for file map)
study/sample.lock.json           the frozen task sample (salt + order) — never re-drawn
runs/                            run artifacts (gitignored; trajectories, sidecar logs)
```

## Quickstart

```bash
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python openai mini-swe-agent pytest
git clone --depth 1 https://github.com/datacurve-ai/deep-swe
echo 'LITELLM_KEY=<your key>' > .env          # never committed
.venv/bin/python -m pytest study/tests -q     # 10 offline tests, no API
.venv/bin/python -m study.preflight           # E00: $0.05 — caching / thinking / cost checks
.venv/bin/python -m study.sample              # draw the frozen sample
.venv/bin/python -m study.driver census       # E1: ~$25 — length census (needs Docker)
.venv/bin/python -m study.e1_report           # distribution, real $/run, peaks for the grid
.venv/bin/python -m study.replay 'runs/E1-*'  # E2: $0 — calibrate budget fractions
.venv/bin/python -m study.driver grid         # E5+E6: the budget sweep
.venv/bin/python -m study.verify runs/E5-*    # score with each task's own verifier
.venv/bin/python -m study.analysis.repricing  # E7: $0 — four billing regimes
```

Guardrails (frozen): no step cap (DeepSWE's own protocol), **$7 cost cap per
run**, 9,000 s wall clock, cumulative spend gates with a global $180 abort.

## Status

Pipeline proven end-to-end against the real benchmark (agent → proxy →
caching → container → patch collection → verifier → graded score). E1 census
in progress. See `docs/DECISIONS.md` for the full decision log.
