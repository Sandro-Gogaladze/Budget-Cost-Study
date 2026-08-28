# Methodology

This file is the prose companion to the plan
([context-budget-study.html](context-budget-study.html) — open it in a
browser; it is the single source of truth and supersedes the earlier volumes).

## The framing, and why it survives review

The hardest attack on a compaction study is *"your threshold is artificial."*
Here the threshold **is** the object of study: every production agent already
sets one, and we **sweep** it rather than fixing it, so no single value can be
called cherry-picked. Measurement papers that characterise a failure get
accepted; papers that bundle a fix (ACON, ReSum) get rejected. We measure.

## The intervention (one method, no mutation)

mini-swe-agent is deliberately linear: `self.messages` is both the trajectory
record and the model input, and `DefaultAgent.query()` passes it verbatim.
`ContextManagedAgent` overrides only `query()`:

- build a **derived view** of the log (never mutate it),
- send the view, append the response to the full log,
- record usage (incl. cached tokens) per step.

Because the uncompacted log survives in every arm, three things are free
forever: offline replay of any budget against any trajectory, cost re-pricing
under different billing regimes, and a future memory-axis analysis over the
stored summary notes (`note_texts` is logged verbatim for exactly this reason).

## Sampling: random, unfiltered, nested

`ORDER = sorted(task_ids, key=sha256(salt + id))`, study set = `ORDER[:12]`.

- **No filtering on difficulty.** Screening tasks on control-arm pass rate
  selects on the outcome measured with the same noise as the outcome; lucky
  always-fail tasks enter, regress to the mean on fresh runs, and make the
  control arm look artificially inconsistent — biasing H1's exact contrast.
- **No filtering on length.** Long runs are where compaction matters;
  selecting short tasks selects away from the phenomenon. Cost is bounded by
  a *uniform* cap applied identically to every arm instead.
- **Nested.** `ORDER[:24]` is a strict superset of `ORDER[:12]`; seeds extend
  the same way. Extension never invalidates a paid run. Re-drawing the sample
  because it looks expensive is forbidden (that is length filtering through
  the back door); the rule is **reduce K, never the sample**.

## Budgets: absolute (decision 2026-08-28)

One token value per level for **every** task — the production knob. The
earlier per-task-fraction design was cleaner dose control but a task-level
oracle no engineer can set. Consequences, accepted knowingly: at any absolute
budget the short tasks never compact (arms identical there), so the treated
share is reported per level, the power simulation models the dilution, and
H1's contrast is pre-declared on treated tasks — legitimate because treatment
status is determined by task length, a pre-treatment covariate.

Values are picked by free replay (E2) against E1's measured peaks and then
frozen: TIGHT = largest value with ≥1 compaction on ≥75% of tasks and ≥3 on
≥50%; LOOSE = a value treating 30–50%; both must exceed 2.5× every head, keep
median treated view ≥1.5× head, and trip the overflow guard on <10% of steps.

## Metrics

- `pass¹` — mean verifier reward. `partial` — the verifier's own graded
  F2P/P2P score (crucial at a ~37% model: failing runs still carry signal).
- `all@k` — fraction of tasks passing **all** k seeds (deliberately renamed
  from pass^k; it is not the standard pass@k).
- **`Δ = pass¹ − all@k`** — the inconsistency. H1's endpoint is
  Δ(SUM) − Δ(RET) at TIGHT, paired within task, task-level bootstrap
  (10,000 resamples). *Why not a variance ratio:* for Bernoulli outcomes mean
  within-task variance is bounded by `m − m² − Var_tasks(p) ≤ 0.25`, so
  "≥2× the variance at equal means" is nearly unsatisfiable even when true.
- **cost-of-pass** = mean $ per run ÷ pass¹ — expected dollars per correct
  answer; infinite at zero accuracy, which is the honest way to price an arm
  that saves tokens by failing.

## Fairness rules

- Whatever tuning effort SUMMARIZE gets, RETRIEVE gets the same, on the same
  data, frozen and hashed the same day (`retriever_cfg_hash`,
  `slot_prompt_hash` stamped on every run row). A weak retriever is a strawman
  *and* breaks H1 mechanically.
- The summarizer's own token cost counts toward its arm's cost limit —
  otherwise the suspect arm quietly gets more compute than its comparators.
- Truncations (`cost_limit` / `timeout`) score 0 **and** are reported as
  per-arm rates: if one arm truncates more, that is a result, not a nuisance.
- `SUMMARIZE_T0` (temperature-0 summarizer) answers "your variance is just the
  extra stochastic call"; its actual t=0 exact-match rate is *measured*
  (hosted APIs are not deterministic) and reported as a number, not a claim.

## Experiment order and gates

E00 preflight ($0.05) → E0 pipeline gate → E1 census (length distribution +
control-arm seed 0 + reproduction check, one pass) → E2 replay calibration
($0) → E3 offline tuning freeze ($0) → E4 analysis plan + power ($0) →
E5 grid (TIGHT block first, so an interrupted campaign still answers the
primary contrast) → E6 determinism control → E7 re-pricing ($0). Every
experiment has a written gate; cumulative spend gates stop the campaign at
$45 / $155 / $180 regardless of anything else.
