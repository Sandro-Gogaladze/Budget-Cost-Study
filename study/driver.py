"""Run driver: E1 census and the E5/E6 grid, with spend gates on every launch.

Runs tasks through mini-swe-agent directly (text-based model — no tool schema,
so implicit caching engages) inside each task's own Docker container.

  E1:  .venv/bin/python -m study.driver census
  E5:  .venv/bin/python -m study.driver grid
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from minisweagent.environments.docker import DockerEnvironment
from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel

from study import config as C
from study.agent import ContextManagedAgent
from study.sample import study_sample
from study.sidecar import Sidecar, extract_usage
from study.spend import Ledger
from study.summarizer import make_summarizer

SYSTEM_TEMPLATE = """You are a software engineering agent working in a sandboxed shell \
at /app, which contains the repository you must modify.
In each reply, think briefly, then give exactly ONE bash command in a ```bash fenced block.
The command's output will be returned to you. Long outputs are truncated, so prefer \
targeted commands (grep -n, sed -n, head). When you are confident the task is complete, reply with
```bash
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
```"""

ACTION_REGEX = r"```bash\s*\n(.*?)\n```"

INSTANCE_TEMPLATE = "{{task}}"


def _task_dir(task_id: str) -> Path:
    return Path(C.DEEPSWE_DIR) / "tasks" / task_id


def _read_instruction(task_id: str) -> str:
    return (_task_dir(task_id) / "instruction.md").read_text()


def _task_meta(task_id: str) -> dict:
    import tomllib
    with open(_task_dir(task_id) / "task.toml", "rb") as f:
        return tomllib.load(f)


def _docker_image(task_id: str) -> str:
    """The pinned prebuilt image from task.toml (public ECR) — pull, don't build."""
    return _task_meta(task_id)["environment"]["docker_image"]


def _collect_patch(env, task_id: str, out_dir: str) -> str | None:
    """Run the task's collect command in the agent container; copy model.patch out."""
    meta = _task_meta(task_id)
    # mini-swe-agent never commits, but the task's collect diffs base..HEAD —
    # commit the working tree first or every patch comes back empty.
    env.execute({"command": "cd /app && git add -A && "
                            "git -c user.email=agent@study -c user.name=agent "
                            "commit -m agent-work --allow-empty -q; true"})
    for step in meta.get("verifier", {}).get("collect", []):
        env.execute({"command": step["command"]})
    r = subprocess.run(["docker", "cp", f"{env.container_id}:/logs/artifacts/model.patch",
                        os.path.join(out_dir, "model.patch")], capture_output=True, text=True)
    return os.path.join(out_dir, "model.patch") if r.returncode == 0 else None


def _cfg_hash(name: str) -> str | None:
    path = os.path.join(C.RUNS_DIR, f"{name}.json")
    if os.path.exists(path):
        return json.load(open(path)).get("hash")
    return None


def _slot_hash() -> str:
    from study.summarizer import SLOT_PROMPT
    return hashlib.sha256(SLOT_PROMPT.encode()).hexdigest()[:12]


def make_model(model_name: str):
    import litellm
    pr = C.PRICES[model_name]
    litellm.register_model({C.litellm_name(model_name): {
        "input_cost_per_token": pr["in"] / 1e6,
        "output_cost_per_token": pr["out"] / 1e6,
        "cache_read_input_token_cost": pr["cached_in"] / 1e6,
        "litellm_provider": "openai", "mode": "chat",
        "max_input_tokens": 1_000_000, "max_output_tokens": 65_536,
    }})
    kwargs = {
        "api_key": os.environ[C.KEY_ENV],
        "api_base": C.PROXY_BASE_URL,
        "temperature": 0.5,
        # 16K: Gemini's thinking regularly runs 3-4K tokens and must fit UNDER the
        # ceiling with room for the visible reply — at 4096 deep thoughts were
        # truncated to zero visible content (observed: RepeatedFormatError, E1 task 1).
        "max_tokens": 16384,
        "timeout": 120,        # break hung HTTP calls (observed: a call stalled >6 min)
        "num_retries": 3,      # then retry; mini's own retry wraps this too
    }
    if C.REASONING_EFFORT:
        kwargs["extra_body"] = {"reasoning_effort": C.REASONING_EFFORT}
    return LitellmTextbasedModel(model_name=C.litellm_name(model_name),
                                 model_kwargs=kwargs, action_regex=ACTION_REGEX)


def run_one(task_id: str, *, strategy: str, budget_tokens, seed: int,
            model_name: str, block: str, ledger: Ledger, peak_full: int | None = None) -> dict:
    ledger.check(block)                                   # spend gate BEFORE launching
    run_id = f"{block}-{task_id}-{strategy}-{seed}-{int(time.time())}"
    sc = Sidecar(run_id)
    image = _docker_image(task_id)
    env = DockerEnvironment(image=image, cwd="/app", timeout=120,
                            run_args=["--network", "none"])  # task.toml agent spec
    agent = ContextManagedAgent(
        make_model(model_name), env,
        summarize_fn=make_summarizer(model_name),
        sidecar=sc,
        system_template=SYSTEM_TEMPLATE, instance_template=INSTANCE_TEMPLATE,
        step_limit=C.STEP_LIMIT, cost_limit=C.COST_LIMIT_USD,
        wall_time_limit_seconds=C.WALL_TIME_S,
        strategy=strategy, token_budget=budget_tokens,
        keep_recent=C.KEEP_RECENT, summ_temperature=C.SUMM_TEMPERATURE,
        output_path=Path(sc.dir) / "live_trajectory.json",   # mini saves after EVERY step
    )
    t0 = time.time()
    exit_status, error = "", ""
    try:
        info = agent.run(task=_read_instruction(task_id))
        exit_status = info.get("exit_status", "")
    except Exception as e:                                # noqa: BLE001
        exit_status, error = "infra_error", repr(e)[:500]
    finally:
        patch_path = None
        try:
            patch_path = _collect_patch(env, task_id, sc.dir)
        except Exception as e:                            # noqa: BLE001
            error = (error + f" collect:{e!r}")[:800]
        usd = agent.cost + agent.vstate.summarizer_cost_usd
        steps_usage = [extract_usage(m) for m in agent.messages if m.get("role") == "assistant"]
        row = dict(
            task_id=task_id, strategy=strategy, budget_tokens=budget_tokens, seed=seed,
            retriever_cfg_hash=_cfg_hash("retriever_cfg"), slot_prompt_hash=_slot_hash(),
            model_id=model_name, model_pinned_at=C.MODEL_PINNED_AT,
            reasoning_effort=C.REASONING_EFFORT, exit_reason=exit_status, error=error,
            steps=agent.n_calls, wall_s=round(time.time() - t0, 1),
            agent_cost_usd=round(agent.cost, 6),
            summarizer_cost_usd=round(agent.vstate.summarizer_cost_usd, 6),
            total_cost_usd=round(usd, 6),
            compactions=agent.vstate.compactions,
            events=agent.vstate.events,
            peak_full_tokens=peak_full, patch=patch_path,
            prompt_tokens=sum(u["prompt_tokens"] for u in steps_usage),
            cached_tokens=sum(u["cached_tokens"] for u in steps_usage),
            completion_tokens=sum(u["completion_tokens"] for u in steps_usage),
            reasoning_tokens=sum(u["reasoning_tokens"] for u in steps_usage),
        )
        sc.finish(**row)
        sc.save_trajectory(agent.messages)
        ledger.add(usd, block, run_id)
        try:
            env.cleanup()
        except Exception:
            pass
    print(json.dumps({k: row[k] for k in ("task_id", "strategy", "seed", "exit_reason",
                                          "steps", "total_cost_usd", "compactions")}))
    return row


def census(model_name: str = C.PRIMARY_MODEL, workers: int = 3) -> None:
    """E1: seed 0 at FULL over the sample (these runs ARE control-arm seed 0).

    Pipelined: one puller thread fetches images in order while N workers run
    tasks whose image is ready. Images are KEPT (disk checked at 82GB free;
    the grid needs every one of them again). Resumable: finished tasks skipped.
    """
    import queue
    import threading
    from concurrent.futures import ThreadPoolExecutor

    ledger = Ledger()
    done = _already_done()
    todo = [t for t in study_sample()
            if (t, "FULL", None, 0, model_name) not in done]
    for t in study_sample():
        if t not in todo:
            print("skip (done):", t, flush=True)

    ready: queue.Queue = queue.Queue()

    def puller():
        for t in todo:
            img = _docker_image(t)
            print("pull", img, flush=True)
            subprocess.run(["docker", "pull", "-q", img], check=False,
                           capture_output=True, text=True, timeout=3600)
            ready.put(t)
        for _ in range(workers):
            ready.put(None)                       # poison pills

    threading.Thread(target=puller, daemon=True).start()

    def worker():
        while True:
            t = ready.get()
            if t is None:
                return
            run_one(t, strategy="FULL", budget_tokens=None, seed=0,
                    model_name=model_name, block="E1", ledger=ledger)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in [ex.submit(worker) for _ in range(workers)]:
            f.result()


def _budget(task_id: str, level: str, peaks: dict, heads: dict) -> int:
    return max(int(C.BUDGET_FRACS[level] * peaks[task_id]),
               int(C.HEAD_FLOOR_MULT * heads[task_id]))


def _evict_image(task_id: str, keep: set[str]) -> None:
    """Free disk: drop the task image once its runs are done (unless shared)."""
    img = _docker_image(task_id)
    if img not in keep:
        subprocess.run(["docker", "rmi", img], capture_output=True, text=True)


def _done_key(r: dict) -> tuple:
    return (r["task_id"], r["strategy"], r.get("budget_tokens"), r["seed"], r["model_id"])


def _already_done() -> set[tuple]:
    """Resume support: skip cells that already have a finished run.json."""
    import glob as _g
    done = set()
    for d in _g.glob(os.path.join(C.RUNS_DIR, "E*-*")):
        if not os.path.isdir(d):
            continue
        try:
            r = json.load(open(os.path.join(d, "run.json")))
            if r.get("exit_reason") not in ("infra_error", ""):
                done.add(_done_key(r))
        except (OSError, json.JSONDecodeError):
            continue
    return done


def grid() -> None:
    """E5+E6, task-major so each image is pulled once then evicted (§07).

    Cell order per task: TIGHT (primary contrast) -> T0 -> LOOSE -> FULL top-up.
    Resumable: finished cells are skipped, so an interrupted campaign continues.
    """
    ledger = Ledger()
    peaks = json.load(open(os.path.join(C.RUNS_DIR, "peaks.json")))
    heads = json.load(open(os.path.join(C.RUNS_DIR, "heads.json")))
    done = _already_done()
    for task_id in study_sample():
        cells: list[tuple[str, int | None, str]] = []
        for strategy in ("SUMMARIZE", "RETRIEVE"):
            cells.append((strategy, _budget(task_id, "TIGHT", peaks, heads), "E5"))
        cells.append(("SUMMARIZE_T0", _budget(task_id, "TIGHT", peaks, heads), "E6"))
        for strategy in ("SUMMARIZE", "RETRIEVE"):
            cells.append((strategy, _budget(task_id, "LOOSE", peaks, heads), "E5"))
        cells.append(("FULL", None, "E5"))
        for strategy, budget, block in cells:
            for seed in range(C.K_SEEDS):
                if strategy == "FULL" and seed == 0:
                    continue                      # E1 already provides FULL seed 0
                row_key = (task_id, strategy, budget, seed, C.PRIMARY_MODEL)
                if row_key in done:
                    continue
                run_one(task_id, strategy=strategy, budget_tokens=budget, seed=seed,
                        model_name=C.PRIMARY_MODEL, block=block, ledger=ledger,
                        peak_full=peaks.get(task_id))
        _evict_image(task_id, keep=set())


if __name__ == "__main__":
    {"census": census, "grid": grid}[sys.argv[1]]()
