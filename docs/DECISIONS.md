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
| 2026-08-28 | **User:** budgets are ABSOLUTE token values (one per level for all tasks), not per-task fractions | the production knob is absolute; per-task fractions are a task-level oracle. Cost accepted: untreated short tasks dilute H1 (treated share reported per level; power sim models it; H1 contrast restricted to treated tasks — length is a pre-treatment covariate, so this is not outcome selection). E2 picks the values from E1's peak distribution; then frozen |
| 2026-08-28 | **User: STOP after E1.** Census complete (12/12, $50 all-in); measured economics (mean $3.24/FULL run, treatment $1.5–4.8 by budget) price the planned grid at $300–450 — unfundable under the $200 cap. Study frozen in a resumable state; grid runs when funding returns | results/E1.md is the archived census; recommended restart shape: TIGHT=48K, SUM vs RET, K=3 (~$125) + T0 at K=1 (~$20), or the full 2-budget grid at ~$350 with real funding |
| 2026-08-29 | **User: primary model switched to `gemini/gemini-3.1-flash-lite`.** L0 preflight: caching verified through the proxy (billing honors it), input exactly $0.25/M, no default thinking. Makes the full grid fundable (~$80–120) inside the remaining budget. Gate: the Lite census must show ≥4 tasks with graded partial in [0.2,0.9] or solves, else Lite is floor-bound and the study reverts to the funding plan. 3.5 Flash census retained as the stronger-generation comparison; budgets will be re-picked from Lite's own peak distribution | model change re-bases the study; nothing from the 3.5 census is reused as Lite data |
| 2026-08-29 | **Protocol v4: native tool-calling** (mini's `LitellmModel` + bash tool), replacing the text-fence protocol; compaction operates on atomic **turn groups** (assistant tool-call + its tool results are never split) | Flash-Lite refuses the text protocol — it hallucinated a `bash` tool with empty text content. L0b measured that implicit caching SURVIVES declared tools through this proxy on both models (Lite: 8,165/11,823 cached, bill $0.00298→$0.00114), so the original reason for text-based is void. Orphaned tool messages are API errors, hence group-atomic views. The 3.5 Flash census (results/) was text-protocol: cross-model comparisons carry that caveat |
