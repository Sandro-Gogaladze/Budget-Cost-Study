# Context Budget Study — implementation

Companion code to `docs/context-budget-study.html` (the plan). Section numbers below refer to it.

## Layout
| file | plan § | what |
|---|---|---|
| `config.py` | — | frozen constants: sample salt, MEASURED price table, budget fractions, spend gates |
| `sample.py` | §03 | deterministic nested task ordering → `sample.lock.json` (never re-draw) |
| `preflight.py` | §04 | E00: caching-through-proxy / thinking / cost-reporting checks |
| `spend.py` | §07 | ledger + per-block gates + $180 global abort |
| `tokens.py` | §06 | self-calibrating token estimator (observes real prompt_tokens) |
| `strategies.py` | §06 | **pure** view builders: FULL / PRUNE / RETRIEVE / SUMMARIZE(+T0) |
| `summarizer.py` | §06 | SLOT_PROMPT summarizer + $0 replay simulator |
| `agent.py` | §06 | `ContextManagedAgent` — overrides only `query()`; log never mutated |
| `sidecar.py` | §08 | runs/steps jsonl; mines cached/reasoning tokens from persisted responses |
| `driver.py` | §07 | E1 census + E5/E6 grid; pulls pinned ECR images; collects model.patch |
| `verify.py` | §07 | builds each task's `tests/` image, runs `test.sh`, merges reward+partial |
| `replay.py` | §07 | E2: budget-fraction sweep over saved trajectories, $0 |
| `analysis/metrics.py` | §09 | pass1 · all@k · Δ gap · cost-of-pass · paired task bootstrap |
| `analysis/repricing.py` | §07 | E7: observed / no-cache / cold / batch regimes, $0 |
| `tests/` | — | offline suite (10 tests) — run before anything paid |

## Status (2026-08-28)
- [x] E00 pre-flight — **all three checks PASS**: caching survives the proxy
  (8,169 cached tok on repeats); cost headers present (`x-litellm-response-cost`,
  `x-litellm-key-spend`); thinking is real (default ≈25× text tokens,
  `reasoning_effort:"minimal"` zeroes it, `"low"` silently ignored).
- [x] Measured prices (frozen 2026-08-28): **in $1.50/M · cached $0.15/M · out $9.00/M**
  — 5× the planning guess; E1 re-forecasts run costs.
- [x] Sample drawn: `sample.lock.json` (salt `gaia-2026-08`, ORDER[:12]).
- [x] deep-swe cloned (116 tasks); envs are **prebuilt ECR images** (pull, no build);
  verifier reports a native `partial` score (graded signal — better than ctrf parsing).
- [x] Key in project `.env` (chmod 600, gitignored); config auto-loads it.
- [x] End-to-end smoke PASSED (python:3.11-slim, `Submitted`, $0.0088): fixes en route —
  registered proxy model prices with litellm, `action_regex` for ```bash fences,
  finish sentinel `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`, action-dict env API,
  `--network none` agent containers per task.toml.
- [x] Power simulation (paired, unfiltered mix): n=12 K=3 → ~21–29% power on the
  Δ-gap ⇒ H1 stays a pilot ESTIMATE at $200; confirmation needs ~n=24 K=5
  (51–66%). Adding tasks beats adding seeds; K=10 buys nothing over K=5.
- [ ] E0 real-task run in flight (abs-module-cache-flags, FULL) → then `verify`,
  then `python -m study.driver census` (E1, ~$25).

## Run order
```bash
source .venv/bin/activate && export LITELLM_KEY=…   # never in a file
python -m study.preflight          # E00  $0.05  done ✓
python -m study.sample             # draw  $0    done ✓
python -m study.driver census      # E1   ~$25   needs docker up
python -m study.replay 'runs/E1-*' # E2    $0    sets fractions + predicts E5 cost
python -m study.driver grid        # E5  ~$104   TIGHT block first
python -m study.verify runs/E5-*   # score      docker, no API
python -m study.analysis.repricing # E7    $0
```
