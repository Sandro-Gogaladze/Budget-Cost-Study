"""ContextManagedAgent (§06): subclass of mini-swe-agent v2 DefaultAgent.

The one rule: NEVER mutate self.messages. query() builds a derived view,
sends the view, and appends the response to the full log — so every run in
every arm keeps a complete uncompacted trajectory (replay, re-pricing, and a
future memory analysis all depend on that).

Verified against mini-swe-agent 2.4.6: DefaultAgent.query() passes
self.messages verbatim to model.query(); we override only that call site.
"""
from __future__ import annotations

import time

from minisweagent.agents.default import AgentConfig, DefaultAgent

from study.sidecar import Sidecar, extract_usage
from study.strategies import ViewState, build_view
from study.tokens import CalibratedEstimator


class ContextManagedAgentConfig(AgentConfig):
    strategy: str = "FULL"                # FULL | PRUNE | SUMMARIZE | SUMMARIZE_T0 | RETRIEVE
    token_budget: int | None = None       # None => native window (FULL control)
    keep_recent: int = 4
    summ_temperature: float = 0.3


class ContextManagedAgent(DefaultAgent):
    def __init__(self, model, env, *, summarize_fn=None, sidecar: Sidecar | None = None, **kwargs):
        super().__init__(model, env, config_class=ContextManagedAgentConfig, **kwargs)
        self.summarize_fn = summarize_fn
        self.sidecar = sidecar
        self.est = CalibratedEstimator()
        self.vstate = ViewState()
        self._last_view: list[dict] | None = None

    # -- the entire intervention -------------------------------------------
    def query(self) -> dict:
        # limits: replicate DefaultAgent's checks (they live inside query()),
        # with summarizer cost counted into the run's own total (§06).
        total_cost = self.cost + self.vstate.summarizer_cost_usd
        if 0 < self.config.step_limit <= self.n_calls or 0 < self.config.cost_limit <= total_cost:
            from minisweagent.agents.default import LimitsExceeded
            raise LimitsExceeded({"role": "exit", "content": "LimitsExceeded",
                                  "extra": {"exit_status": "LimitsExceeded", "submission": ""}})
        if 0 < self.config.wall_time_limit_seconds <= int(time.time() - self._start_time):
            from minisweagent.agents.default import TimeExceeded
            raise TimeExceeded({"role": "exit", "content": "TimeExceeded",
                                "extra": {"exit_status": "TimeExceeded", "submission": ""}})

        view = build_view(
            self.messages,
            strategy=self.config.strategy,
            budget_tokens=self.config.token_budget,
            est=self.est,
            state=self.vstate,
            keep_recent=self.config.keep_recent,
            summarize_fn=self.summarize_fn,
            summ_temperature=self.config.summ_temperature,
        )
        self._last_view = view
        self.n_calls += 1
        message = self.model.query(view)              # the model sees the VIEW…
        self.cost += message.get("extra", {}).get("cost", 0.0)
        self.add_messages(message)                    # …the log keeps EVERYTHING

        u = extract_usage(message)
        self.est.observe(view, u["prompt_tokens"])    # self-calibrate the estimator
        if self.sidecar:
            self.sidecar.step(
                step_idx=self.n_calls,
                view_tokens=u["prompt_tokens"] or self.est.tokens(view),
                view_msgs=len(view),
                log_tokens=self.est.tokens(self.messages),
                log_msgs=len(self.messages),
                compactions=self.vstate.compactions,
                **u,
            )
        return message
