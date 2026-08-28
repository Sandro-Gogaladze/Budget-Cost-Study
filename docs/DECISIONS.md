# Decision log

Frozen decisions, dated. Changes after the analysis plan is filed are
deviations and must be recorded here with their date.

| Date | Decision | Rationale |
|---|---|---|
| 2026-08-28 | Benchmark: DeepSWE only; Gaia2 deferred to a later generalization arm | verifier audit (1.4% disagreement) removes the need for a second benchmark; Gaia2's typical 19K context can't exercise realistic budgets |
| 2026-08-28 | Memory axis (planted facts) deferred; `note_texts` logged verbatim anyway | keeps the axis answerable later, offline, for $0 |
| 2026-08-28 | Model: Gemini 3.5 Flash primary (37% baseline ≈ max p(1−p)); Flash-Lite only as an E1 bake-off; preview endpoints banned | consistency effects are easiest to detect mid-range; preview models can change under a study |
| 2026-08-28 | Sample: salt `gaia-2026-08`, `ORDER[:12]`, unfiltered, nested; never re-drawn | see METHODOLOGY §Sampling |
| 2026-08-28 | Budgets relative to each task's peak: LOOSE 60% · TIGHT 20% · floor 2.5×head | equal compaction pressure across an unfiltered sample |
| 2026-08-28 | H1 endpoint: Δ = pass¹ − all@k gap (not a variance ratio) | Bernoulli ceiling makes a variance ratio nearly unsatisfiable |
| 2026-08-28 | H1 reported as pilot estimate with CI (n=12, K=3 → ~21–29% power); H2 (cost-of-pass U) carries the study | measured power, measured costs |
| 2026-08-28 | **User:** no step cap (DeepSWE's own protocol); wall clock 9,000 s | match the benchmark's published conditions |
| 2026-08-28 | **User:** per-run cost cap **$7**, identical in every arm, summarizer cost included | sole runaway guard |
| 2026-08-28 | `max_tokens` 16,384 (was 4,096) | at 4,096 Gemini's thinking (~3.9K tokens) was truncated to zero visible content → spurious RepeatedFormatError; a harness defect, so all E1 runs restarted under one config |
| 2026-08-28 | Text-based model class (no tool schema) | tool schemas defeat Gemini implicit caching |
| 2026-08-28 | Price table frozen (measured from proxy billing): in $1.50/M · cached $0.15/M · out $9.00/M | reconciled against `x-litellm-response-cost` |
| 2026-08-28 | E0 run reclassified calibration-only (`runs/CAL-*`) | ran under old capped config; mixing it into the control arm would be a silent inconsistency |
| 2026-08-28 | Census parallelism: 3 workers + image prefetch; images kept on disk | ~4–6× wall clock; 82GB free covers all 12 images; the grid reuses them |
| 2026-08-28 | Config v3: accept ```sh as well as ```bash; corrective format-error template (shows the exact required fence + heredoc rule); same rule added to the system prompt; `RepeatedFormatError` never counts as a finished run | the default error message ("provide EXACTLY ONE action") cannot teach the fence contract — observed drift to ```python fences at step 74; harness-contract failures are reruns, not results |
