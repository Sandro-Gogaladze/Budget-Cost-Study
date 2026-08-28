# Budget-Cost-Study

**What does the context budget cost a long-running coding agent?**

> 📄 **The authoritative plan is [`docs/context-budget-study.html`](docs/context-budget-study.html)** —
> open it in a browser (or the live artifact copy:
> <https://claude.ai/code/artifact/d4926830-ffe2-4122-b6bc-1d0a5ddbb394>).
> This README is the working summary; where they disagree, the plan wins.
> Superseded earlier plan volumes live in [`docs/archive/`](docs/archive/).

---

## 1. The idea

Every deployed agent (Claude Code, Codex, LangChain agents…) sets a token
budget and **compacts** its history — usually by summarizing — when the
history exceeds it. That budget is a real engineering knob that every
production system sets **by guessing**. The industry already believes "max
context isn't best" (Codex reportedly caps ~300K of a 1M window; Claude Code
compacts well below its limit), but nobody has measured where the good range
is.

**We measure it.** We sweep the budget from loose to tight on real, long,
auto-graded coding tasks and measure three axes:

| Axis | Question | Metric |
|---|---|---|
| **Success** | does tightening the budget lower the solve rate? | verifier `reward` + graded `partial` (F2P/P2P) |
| **Reliability** | does the agent get *less consistent* run-to-run? | `Δ = pass¹ − all@k` (the inconsistency gap) |
| **Cost** | where are dollars-per-**correct**-answer minimised? | cost-of-pass, cache-adjusted |

We do **not** build a better summarizer. The measurement is the contribution —
sweeping the knob answers "isn't your threshold artificial?" by making the
threshold the object of study. (The memory axis — planted facts, what
summarization destroys — is deferred, but `note_texts` is logged verbatim on
every run so it can be added later offline for $0.)

### The two hypotheses (falsifiable; filed before confirmatory runs)

- **H1 · Reliability** — at tight budgets summarizing keeps a *similar
  average* success to retrieval but becomes far less consistent:
  `Δ(SUMMARIZE) > Δ(RETRIEVE)` at TIGHT while mean success overlaps.
  *At this pilot's size H1 is reported as an estimate with a CI, never as a
  hypothesis test (measured power: 21–29% at n=12, K=3).*
- **H2 · Cost** — raw dollars fall monotonically as the budget tightens
  (caching arithmetic, §5), accuracy falls too, so **cost-of-pass is U-shaped
  with an interior minimum**. That minimum's location is the *economically
  optimal context budget* — the headline. Falsified if monotone, which is
  itself the practical answer ("always compact" / "never compact").

---

## 2. The experiment plan (E00 → E7)

Total campaign: **~230 runs, ≈$160 planned, hard-capped at $200.**
Every experiment has a *gate* — a written decision rule. Four experiments are
free. Cumulative spend gates stop the campaign at $45 / $155 / $180 no matter
what.

| # | Experiment | What it does | Size / cost | Gate (decision rule) |
|---|---|---|---|---|
| E00 | **Pre-flight** | 3 identical big calls through the proxy: does implicit caching survive it? thinking tokens? cost reporting? | $0.05 | cached_tokens > 0 on repeats, else cost axis is *modelled* not *measured* — re-plan |
| E0 | **Pipeline gate** | one real DeepSWE task end-to-end: agent → container → patch → verifier | ~$2 | every layer green once; bugs fixed here are cheap |
| E1 | **Census** | all 12 sampled tasks, FULL, seed 0, uncapped — the length/cost distribution nobody has published; doubles as control-arm seed 0 and the leaderboard reproduction check | ~$15–35 | ≥25 tasks… n/a at 12 — gate is: measured $/run sets the n×K allocation (rule: **n before K; reduce K, never the sample**) |
| E2 | **Replay calibration** | sweep budget *fractions* offline through `build_view()` against E1 trajectories; predict the grid's cost before paying for it | **$0** | acceptance test: LOOSE ≥30% compact ≥1×; TIGHT ≥80% compact ≥3×, median view ≥1.5× head, overflow <10% of steps; predicted E5 ≤ $110 |
| E3 | **Offline tuning + freeze** | tune RETRIEVE (recall of needed-later turns) and SUMMARIZE (slot-prompt retention) with *equal recorded effort*; freeze + hash both | **$0** | `retriever_cfg_hash` + `slot_prompt_hash` frozen the same day, stamped on every later run |
| E4 | **Analysis plan + power** | binomial power simulation (paired, unfiltered mix); file the pilot analysis plan | **$0** | plan filed *before* E5; endpoints, exclusions, sampling salt, hashes all frozen; later changes are dated deviations |
| E5 | **The grid** | SUMMARIZE + RETRIEVE × {LOOSE, TIGHT} × 12 tasks × K=3, plus FULL seeds 1–2 (seed 0 comes from E1) | ~168 runs, ~$104 | run TIGHT **first** (carries the primary contrast); health check after TIGHT: truncation <20%/arm, no arm >3× another's cost, spend within 25% of E2's prediction |
| E6 | **Determinism control** | SUMMARIZE_T0 × TIGHT × 12 × K=3, plus 100 free-standing t=0 summarizer calls to *measure* the exact-match rate | ~36 runs, ~$20 | if the Δ gap survives at t=0, the reliability signal is compaction itself, not the extra stochastic call |
| E7 | **Cost re-pricing** | re-price every logged run under observed / no-cache / cold / batch regimes; fit the cost-of-pass U and bootstrap its argmin | **$0** | needs `cached_tokens` logged from E0 onward (it is) |

Then: `verify` everything → `analysis.plot` (the one figure: success,
consistency, inverted cost-of-pass vs budget, with the recommended operating
band shaded) → write-up.

**Extension order when more budget arrives** (nested — nothing invalidates a
paid run): seeds 3–4 → MEDIUM budget level (35%) → PRUNE cost-floor arm →
tasks `ORDER[12:24]` → a second model (older generation → the trends result).

---

## 3. Design essentials

**Benchmark — [DeepSWE](https://github.com/datacurve-ai/deep-swe)** (Datacurve,
Apache-2.0): 113 original, contamination-free coding tasks across 91 repos and
5 languages; hand-written program verifiers independently audited at **1.4%**
judge disagreement (vs 32.4% for SWE-Bench Pro). Verifiers also emit a graded
`partial` score — vital at a ~37% model, where most runs fail but still carry
signal. Task images are prebuilt on public ECR (`docker pull`, no build).

**Sample — random, unfiltered, nested** (`study/sample.lock.json`):
`ORDER = sorted(task_ids, key=sha256("gaia-2026-08" + id))`, study =
`ORDER[:12]`. No filtering on difficulty (selecting on control-arm pass rate
biases H1's exact contrast) and none on length (long runs are where compaction
matters). `ORDER[:24]` is a strict superset → clean pooling later.
**Never re-draw. If costs surprise, reduce K.**

**Arms:** `FULL` (true uncompacted control — 1M window covers every task) ·
`SUMMARIZE` (the suspect; slot-structured notes) · `SUMMARIZE_T0` (t=0
control) · `RETRIEVE` (the comparator: current-subgoal query, BM25, pinned
file-writes + recent turns) · `PRUNE` (deferred to first extension — the
zero-overhead cost floor). `FILES`/`EXTRACTIVE` cut (tool-surface change /
memory-axis question).

**Budgets — relative, per task:**
`budget = max(frac × peak_full(task), 2.5 × head(task))`, LOOSE = 60%,
TIGHT = 20%. Equal compaction pressure across a sample whose lengths vary 5×;
"compact at ~X% of your typical peak" transfers across models.

**Guardrails (frozen, per user):** **no step cap** (DeepSWE's own protocol) ·
**$7 cost cap per run** (sole runaway guard, identical in every arm,
summarizer cost included) · **9,000 s wall clock** (DeepSWE's own). Truncated
runs score 0 *and* their rate is reported per arm.

**Fairness:** equal tuning effort for SUMMARIZE and RETRIEVE, frozen+hashed
together; the summarizer's tokens bill against its own arm; every comparison
is paired within task; bootstrap resamples tasks (10,000 draws).

**The intervention** (`study/agent.py`): mini-swe-agent's `query()` is the
single override — it builds a **derived view** of `self.messages` and never
mutates the log, so every run in every arm keeps its full uncompacted
trajectory (this is what makes E2 replay, E7 re-pricing, and any future
memory analysis free).

---

## 4. Measured facts this study stands on (2026-08-28)

- **Implicit caching survives the LiteLLM proxy** and billing honors it
  (identical call: cold $0.0178 → warm $0.0068). On a real 120-step run:
  **89% cache-hit rate** (3.79M of 4.26M prompt tokens cached).
- **Proxy prices, solved from billed costs and frozen:** input **$1.50/M** ·
  cached **$0.15/M** · output **$9.00/M**. Thinking bills as output and
  defaults to ~25× the visible text; `reasoning_effort:"minimal"` zeroes it,
  `"low"` is silently ignored.
- **Power** (paired simulation, unfiltered mix): 12×3 → 21–29% on the Δ-gap;
  ~24×5 → 51–66%. Adding tasks beats adding seeds; K=10 adds nothing over K=5.
- Gemini 3.5 Flash published DeepSWE baseline: **37% pass@1** — near the
  maximum of p(1−p), the easiest place to detect a consistency effect.

## 5. Why cost is the strongest axis

```
cost(call t) ≈ 0.1p·L(t−1) + p·d_t + p_out·out_t     (cached prefix + new suffix)
a compaction voids the cache → next call repays full price on the new view V
break-even m* = 10V/(L−V) ≈ 2–11 calls               (single-digit at tight budgets)
```

So compaction *does* cut raw dollars, monotonically — raw cost is boring.
**Cost-of-pass** (mean $ ÷ pass¹) is the interesting quantity: cost is
*measured exactly* from provider cache counters, so pass¹ is the only noisy
term — which is why H2 is resolvable even at pilot scale.

---

## 6. Repo map

```
docs/context-budget-study.html   THE PLAN — authoritative (open in browser)
docs/METHODOLOGY.md              design rationale, metric defs, fairness rules
docs/DECISIONS.md                dated frozen-decision log (deviations dated too)
docs/archive/                    superseded plan volumes (history)
study/
  config.py       frozen constants: salt, prices, fractions, caps, spend gates
  sample.py       deterministic nested sampling  → sample.lock.json (committed)
  preflight.py    E00 checks                     spend.py    ledger + gates
  tokens.py       self-calibrating estimator     strategies.py  pure view builders
  summarizer.py   slot prompt + $0 simulator     agent.py    the query() override
  sidecar.py      per-step usage capture         driver.py   census + grid (resumable)
  verify.py       task's own verifier → reward   replay.py   E2 offline calibration
  e1_report.py    census → distribution + peaks  power.py    E4 simulation
  tune_retrieve.py E3 offline recall tuning      t0_check.py E6 identity measurement
  watch.py        live run viewer                analysis/   metrics · repricing · plot
  tests/          10 offline tests (no API)
runs/             run artifacts (gitignored): steps.jsonl, run.json, trajectory,
                  model.patch, spend_ledger.jsonl
```

## 7. Continuing the work (pull → run)

```bash
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python openai mini-swe-agent pytest
git clone --depth 1 https://github.com/datacurve-ai/deep-swe
echo 'LITELLM_KEY=<key>' > .env                     # never commit this
.venv/bin/python -m pytest study/tests -q           # sanity: 10 tests, no API
.venv/bin/python -m study.preflight                 # E00 ($0.05) — re-verify caching
.venv/bin/python -m study.driver census             # E1 — resumable, 3 workers
.venv/bin/python -m study.e1_report                 # distribution + peaks.json/heads.json
.venv/bin/python -m study.replay 'runs/E1-*'        # E2 ($0) — fractions + cost forecast
.venv/bin/python -m study.tune_retrieve 'runs/E1-*' # E3 ($0) — freeze retriever
.venv/bin/python -m study.power                     # E4 ($0)
.venv/bin/python -m study.driver grid               # E5+E6 — TIGHT first, resumable
.venv/bin/python -m study.verify runs/E5-* runs/E6-* runs/E1-*
.venv/bin/python -m study.t0_check 'runs/E1-*'      # E6 identity number
.venv/bin/python -m study.analysis.repricing        # E7 ($0)
.venv/bin/python -m study.analysis.plot             # the figure
```

Everything is **resumable**: the driver skips any cell that already has a
finished `run.json` (infra errors and `RepeatedFormatError` are reruns, not
results). Watch a live run with `.venv/bin/python -m study.watch`.
Docker Desktop must be running; peak disk ≈ all 12 task images ≈ 45 GB.

**Rules that keep the study valid** — read [`docs/DECISIONS.md`](docs/DECISIONS.md)
before changing anything:
1. Never re-draw or filter the sample; extend only as prefixes (tasks & seeds).
2. Never tune one arm without giving the other equal effort; configs are
   frozen + hashed before confirmatory runs.
3. Any config change after the analysis plan is filed is a **dated deviation**;
   a harness-contract fix invalidates affected runs → rerun them, uniformly.
4. Caps and prices are identical in every arm, always.

## 8. Hard-won harness lessons (so you don't re-learn them)

- Use the **text-based** mini-swe-agent model class: the default sends a
  native tool schema, which **defeats Gemini implicit caching**.
- `max_tokens` must leave room for thinking **plus** the reply — at 4,096
  Gemini's ~3.9K-token thoughts were truncated to zero visible content
  (spurious `RepeatedFormatError`). We run 16,384.
- The stock format-error message can't teach the fence contract; the model
  drifts to ```python fences. Our corrective template shows the exact
  required shape and the heredoc-inside-bash pattern.
- DeepSWE's collect step diffs **committed** work; mini-swe-agent never
  commits → commit the working tree before collecting or every patch is empty.
- Set a **request timeout** (120 s) on model calls: one hung HTTP connection
  otherwise freezes a run silently, forever.
- Register the proxy's model + measured prices with litellm, or its cost
  tracker crashes; registering also makes `agent.cost` equal the actual bill.
