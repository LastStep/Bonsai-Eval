"""P2.5 validation-run CLI — sweep all 12 scenarios × 3 rungs × 3 seeds.

Plan 38 §P2.5: end-to-end validation of the Bonsai-behavioral suite, capping
spend at ~$20. Produces a parquet at `data/validation/p2-validation-<date>.parquet`
with one row per (scenario, rung, seed) run.

# Seeding caveat (documented limitation)

Inspect AI does NOT expose a deterministic RNG seed parameter on `eval()` —
the `epochs` API has a `reducer`, not a seed knob. Per-run seed values in
this module are therefore CARRIED FORWARD (recorded in the parquet for
auditability + per-run HOME / workspace path-uniqueness) but DO NOT pin
Inspect's sampling RNG. The model's `temperature=0.0` (pinned in
`bonsai_eval.preregistration.ACTIVE_PREREGISTRATION`) reduces this to a
near-deterministic decode path; residual variance comes from CC's
tool-loop nondeterminism (file mtime ordering, network jitter) which a
seed cannot mask anyway.

# Cost tracking

`EvalLog.stats.model_usage` carries per-model token counts at run end.
We multiply by `bonsai_eval.preregistration.ACTIVE_PREREGISTRATION.model`'s
pricing (Haiku 4.5: $1/MTok input, $5/MTok output) to estimate per-run
cost. The budget is enforced as a SOFT cap — when cumulative cost crosses
`--budget-usd`, the sweep aborts gracefully and the in-flight rows are
written out (with `error_msg = "budget exceeded — sweep aborted"` on the
skipped tail).

# Mocking surface for tests

`_invoke_eval` is the single seam unit tests monkeypatch with a synthetic
`EvalResult` factory. NO live `inspect_ai.eval` runs in pytest.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Repo root from `scripts/run_validation.py` = parent of `scripts/`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:  # support `python scripts/run_validation.py`
    sys.path.insert(0, str(_REPO_ROOT))

from bonsai_eval.preregistration import ACTIVE_PREREGISTRATION  # noqa: E402

DEFAULT_SCENARIOS_DIR = _REPO_ROOT / "scenarios" / "bonsai_behavioral"
DEFAULT_RUNS_DIR = _REPO_ROOT / "data" / "raw" / "runs"
DEFAULT_OUTPUT_DIR = _REPO_ROOT / "data" / "validation"

VALID_RUNG_TOKENS: frozenset[str] = frozenset({"r1", "r2", "r3"})
RUNG_TOKEN_TO_NAME: dict[str, str] = {"r1": "rung1", "r2": "rung2", "r3": "rung3"}

# Haiku 4.5 list pricing (USD per million tokens). Used for cost estimation
# + dry-run budget reporting. If pricing changes, update both this constant
# and the dry-run output banner.
_PRICE_INPUT_USD_PER_MTOK = 1.00
_PRICE_OUTPUT_USD_PER_MTOK = 5.00

# Dry-run estimate per (scenario, rung, seed) — Haiku is cheap; assume
# ~10k input + ~2k output tokens per run, well under per-task 8k cap on
# output. This is a coarse upper bound used to print "estimated total
# cost" at dry-run time so the user can sanity-check before spending.
_DRY_RUN_TOKENS_INPUT = 10_000
_DRY_RUN_TOKENS_OUTPUT = 2_000


@dataclass(slots=True)
class RunSpec:
    """One leaf of the (scenario, rung, seed) cartesian product."""

    scenario_id: str
    rung: str  # one of {"rung1", "rung2", "rung3"}
    seed: int

    @property
    def home_dir(self) -> Path:
        return DEFAULT_RUNS_DIR / f"{self.scenario_id}-{self.rung}-{self.seed}-home"

    @property
    def workspace_dir(self) -> Path:
        return DEFAULT_RUNS_DIR / f"{self.scenario_id}-{self.rung}-{self.seed}-ws"


@dataclass(slots=True)
class RunResult:
    """One row of the validation parquet."""

    scenario_id: str
    rung: str
    seed: int
    score: float
    evaluator_details: str  # JSON-encoded list[dict]
    cost_usd: float
    duration_s: float
    error_msg: str
    log_path: str

    @classmethod
    def aborted(cls, spec: RunSpec, msg: str) -> RunResult:
        return cls(
            scenario_id=spec.scenario_id,
            rung=spec.rung,
            seed=spec.seed,
            score=float("nan"),
            evaluator_details="[]",
            cost_usd=0.0,
            duration_s=0.0,
            error_msg=msg,
            log_path="",
        )

    @classmethod
    def errored(cls, spec: RunSpec, exc: BaseException) -> RunResult:
        return cls(
            scenario_id=spec.scenario_id,
            rung=spec.rung,
            seed=spec.seed,
            score=float("nan"),
            evaluator_details="[]",
            cost_usd=0.0,
            duration_s=0.0,
            error_msg=f"{type(exc).__name__}: {exc}",
            log_path="",
        )


@dataclass(slots=True)
class EvalOutcome:
    """Structured result returned by `_invoke_eval` (mockable in tests).

    A thin shim over `inspect_ai.EvalLog` so the production path + the test
    stubs use the same shape. Fields are independent of Inspect's internal
    representation so we can evolve them without breaking tests.
    """

    score: float
    evaluator_details: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    duration_s: float = 0.0
    log_path: str = ""
    error_msg: str = ""


# `EvalInvoker` is the type of the per-run evaluator. Tests monkeypatch
# this module's `_invoke_eval` attribute with a synthetic callable.
#
# Signature: `(spec, model, *, token_limit, time_limit, cost_limit) -> EvalOutcome`.
# All three budget knobs are keyword-only so tests can pass `**budget` dicts
# without positional-arg gymnastics, and so future kwargs (e.g.
# `message_limit`) can be added without breaking existing call sites.
EvalInvoker = Callable[..., EvalOutcome]


def _estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Token counts → USD using the locked Haiku pricing constants above."""
    return (
        input_tokens / 1_000_000 * _PRICE_INPUT_USD_PER_MTOK
        + output_tokens / 1_000_000 * _PRICE_OUTPUT_USD_PER_MTOK
    )


def _list_scenario_ids(scenarios_dir: Path) -> list[str]:
    """Sorted scenario-id list = sorted stem of every YAML in `scenarios_dir`."""
    if not scenarios_dir.is_dir():
        raise FileNotFoundError(f"scenarios dir not found: {scenarios_dir}")
    return sorted(p.stem for p in scenarios_dir.glob("*.yaml"))


def _parse_scenarios_arg(value: str | None, scenarios_dir: Path) -> list[str]:
    """Resolve `--scenarios A,B,C` to a list of ids; `None` → all on disk."""
    available = _list_scenario_ids(scenarios_dir)
    if value is None or value.strip() == "":
        return available
    requested = [s.strip() for s in value.split(",") if s.strip()]
    available_set = set(available)
    bad = [s for s in requested if s not in available_set]
    if bad:
        raise SystemExit(f"unknown scenario ids: {bad}\navailable: {available}")
    return requested


def _parse_rungs_arg(value: str) -> list[str]:
    """Resolve `--rungs r1,r2,r3` to a list of canonical names."""
    tokens = [t.strip() for t in value.split(",") if t.strip()]
    bad = [t for t in tokens if t not in VALID_RUNG_TOKENS]
    if bad:
        raise SystemExit(
            f"unknown rung tokens: {bad}; expected subset of {sorted(VALID_RUNG_TOKENS)}"
        )
    return [RUNG_TOKEN_TO_NAME[t] for t in tokens]


def enumerate_runs(
    scenarios: list[str],
    rungs: list[str],
    seeds: int,
) -> list[RunSpec]:
    """Cartesian product → list of RunSpec, ordered (scenario, rung, seed)."""
    if seeds < 1:
        raise SystemExit(f"--seeds must be >= 1, got {seeds}")
    out: list[RunSpec] = []
    for scenario_id in scenarios:
        for rung in rungs:
            for seed in range(seeds):
                out.append(RunSpec(scenario_id=scenario_id, rung=rung, seed=seed))
    return out


# --- production eval invocation ---------------------------------------------


def _invoke_eval(
    spec: RunSpec,
    model: str,
    *,
    token_limit: int | None = None,
    time_limit: int | None = None,
    cost_limit: float | None = None,
) -> EvalOutcome:
    """Run a single (scenario, rung, seed) via `inspect_ai.eval`.

    Imports Inspect lazily so unit tests (which monkeypatch this function)
    never pay the import cost or trip on `anthropic` being absent. The
    task factory is resolved by name via the `bonsai_eval.tasks.bonsai_behavioral`
    module (each `@task` function is callable as `module.<snake_id>`).

    Budget knobs map to `inspect_ai.eval()` kwargs (verified against
    inspect-ai 0.3.219 signature — all three are first-class):
      - `token_limit`: total tokens budgeted for the task (input + output).
        Caller derives from `args.max_tokens * 20` to cover ~20 tool-call
        rounds; Inspect aborts the task when the total crosses this.
      - `time_limit`: per-task wall-clock cap in seconds. Maps to
        `args.max_task_time_s`.
      - `cost_limit`: USD ceiling enforced by Inspect's cost-tracking
        layer. The CLI forwards the REMAINING budget (`budget_usd -
        cumulative_cost`) so a single overrun run doesn't blow past the
        envelope; the post-hoc soft abort in `run_sweep` is the
        secondary guard.

    `None` for any knob means "no Inspect-level cap" — the caller
    relies on cumulative-cost tracking + post-hoc abort.
    """
    from inspect_ai import eval as inspect_eval  # noqa: PLC0415

    from bonsai_eval.tasks import bonsai_behavioral as tasks_mod  # noqa: PLC0415

    snake = spec.scenario_id.replace("-", "_")
    task_fn = getattr(tasks_mod, snake, None)
    if task_fn is None:
        return EvalOutcome(
            score=float("nan"),
            error_msg=f"no @task function for scenario {spec.scenario_id!r}",
        )

    spec.home_dir.mkdir(parents=True, exist_ok=True)
    spec.workspace_dir.mkdir(parents=True, exist_ok=True)

    task = task_fn(
        rung=spec.rung,
        home_dir=spec.home_dir,
        workspace=spec.workspace_dir,
        seed=spec.seed,
    )

    # Build the kwargs dict so unset knobs don't leak `None` into
    # `inspect_eval` (Inspect treats `None` as "no cap" already, but
    # omitting the kwarg keeps the call site honest and the test
    # assertions sharp).
    eval_kwargs: dict[str, Any] = {"model": model}
    if token_limit is not None:
        eval_kwargs["token_limit"] = token_limit
    if time_limit is not None:
        eval_kwargs["time_limit"] = time_limit
    if cost_limit is not None:
        eval_kwargs["cost_limit"] = cost_limit

    started = _dt.datetime.now(_dt.UTC)
    try:
        logs = inspect_eval(task, **eval_kwargs)
    except Exception as exc:  # noqa: BLE001 — top-level boundary
        return EvalOutcome(
            score=float("nan"),
            error_msg=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[:1000]}",
            duration_s=(_dt.datetime.now(_dt.UTC) - started).total_seconds(),
        )

    if not logs:
        return EvalOutcome(score=float("nan"), error_msg="inspect_eval returned no logs")
    log = logs[0]
    return _outcome_from_log(log, started)


def _outcome_from_log(log: Any, started: _dt.datetime) -> EvalOutcome:
    """Extract token + score data from an `inspect_ai.EvalLog`.

    Defensive: every field is best-effort because Inspect's log shape
    evolves across minor versions. Missing fields fall back to zero
    rather than raising — we'd rather log an under-counted cost than
    abort the sweep.
    """
    duration_s = (_dt.datetime.now(_dt.UTC) - started).total_seconds()
    score = float("nan")
    details: list[dict[str, Any]] = []
    input_tokens = 0
    output_tokens = 0
    log_path = ""
    try:
        log_path = str(getattr(log, "location", "") or "")
        samples = getattr(getattr(log, "samples", None), "__iter__", None)
        if samples is not None:
            for sample in log.samples:
                s = getattr(sample, "scores", None) or {}
                # Take any one score's numeric value; scorers in this repo
                # all return a single composite score per sample.
                for v in s.values():
                    val = getattr(v, "value", None)
                    if isinstance(val, (int, float)):
                        score = float(val)
                    md = getattr(v, "metadata", None) or {}
                    if isinstance(md, dict) and md.get("evaluators"):
                        details = list(md["evaluators"])
                    break
                break  # one sample per task in our suite
        usage = getattr(getattr(log, "stats", None), "model_usage", None) or {}
        for u in usage.values():
            input_tokens += int(getattr(u, "input_tokens", 0) or 0)
            output_tokens += int(getattr(u, "output_tokens", 0) or 0)
    except Exception as exc:  # noqa: BLE001
        return EvalOutcome(
            score=float("nan"),
            error_msg=f"outcome_from_log: {type(exc).__name__}: {exc}",
            duration_s=duration_s,
            log_path=log_path,
        )
    return EvalOutcome(
        score=score,
        evaluator_details=details,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_s=duration_s,
        log_path=log_path,
    )


# --- main sweep -------------------------------------------------------------


def run_sweep(
    specs: list[RunSpec],
    *,
    model: str,
    budget_usd: float,
    token_limit: int | None = None,
    time_limit: int | None = None,
    eval_invoker: EvalInvoker | None = None,
) -> list[RunResult]:
    """Drive the sweep; respect the budget; return one `RunResult` per spec.

    `eval_invoker` defaults to `_invoke_eval` but tests pass a synthetic
    callable. When cumulative cost > budget, remaining specs are emitted
    as aborted rows so the parquet has a full enumeration with explicit
    `budget exceeded` markers on the tail.

    `token_limit` / `time_limit` flow through to `_invoke_eval` unchanged.
    `cost_limit` is computed PER-RUN as the remaining budget envelope —
    each call forwards `max(budget_usd - cumulative_cost, 0.0)`. This
    couples Inspect's in-run cost guard to the sweep-level budget so a
    single runaway run can't burn the entire envelope before
    post-hoc abort kicks in. When the remaining budget is zero we abort
    BEFORE invoking — no point starting a run with a $0 ceiling.
    """
    invoker: EvalInvoker = eval_invoker if eval_invoker is not None else _invoke_eval
    results: list[RunResult] = []
    cumulative_cost = 0.0
    aborted = False
    for spec in specs:
        if aborted:
            results.append(RunResult.aborted(spec, "budget exceeded — sweep aborted"))
            continue
        remaining = max(budget_usd - cumulative_cost, 0.0)
        try:
            outcome = invoker(
                spec,
                model,
                token_limit=token_limit,
                time_limit=time_limit,
                cost_limit=remaining if remaining > 0 else None,
            )
        except Exception as exc:  # noqa: BLE001
            results.append(RunResult.errored(spec, exc))
            continue
        cost = _estimate_cost_usd(outcome.input_tokens, outcome.output_tokens)
        cumulative_cost += cost
        results.append(
            RunResult(
                scenario_id=spec.scenario_id,
                rung=spec.rung,
                seed=spec.seed,
                score=outcome.score,
                evaluator_details=json.dumps(outcome.evaluator_details),
                cost_usd=cost,
                duration_s=outcome.duration_s,
                error_msg=outcome.error_msg,
                log_path=outcome.log_path,
            )
        )
        if cumulative_cost > budget_usd:
            aborted = True
    return results


def write_parquet(results: list[RunResult], output: Path) -> None:
    """Write rows to parquet, creating the parent dir on demand.

    Uses pandas + pyarrow (both already declared in pyproject). We resist
    duckdb here because the canonical schema is a flat table — Parquet is
    the destination, not a query target.
    """
    import pandas as pd  # noqa: PLC0415

    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(r) for r in results]
    df = pd.DataFrame(rows)
    df.to_parquet(output, engine="pyarrow", index=False)


# --- CLI --------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    today = _dt.date.today().isoformat()
    default_output = DEFAULT_OUTPUT_DIR / f"p2-validation-{today}.parquet"
    parser = argparse.ArgumentParser(
        description=(
            "P2.5 end-to-end validation sweep — Plan 38 §P2.5. "
            "Runs the cartesian product of (scenarios × rungs × seeds) and "
            "writes one parquet row per run. Soft-budgets cost at "
            "--budget-usd, aborting cleanly if exceeded."
        )
    )
    parser.add_argument("--seeds", type=int, default=3, help="seeds per (scenario,rung)")
    parser.add_argument(
        "--rungs",
        default="r1,r2,r3",
        help="comma-separated rung tokens (r1,r2,r3)",
    )
    parser.add_argument(
        "--scenarios",
        default=None,
        help="comma-separated scenario ids; default = all on disk",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output,
        help="parquet output path (default templated by date)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
        help="per-task max output tokens (recorded only; pre-reg pins the actual cap)",
    )
    parser.add_argument(
        "--max-task-time-s",
        type=int,
        default=600,
        help="per-task wall-clock cap (seconds, advisory — Inspect enforces via time_limit)",
    )
    parser.add_argument(
        "--budget-usd",
        type=float,
        default=20.0,
        help="soft USD cap; sweep aborts cleanly when exceeded",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="enumerate + cost-estimate without executing",
    )
    parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=DEFAULT_SCENARIOS_DIR,
        help="scenarios directory (default: scenarios/bonsai_behavioral/)",
    )
    parser.add_argument(
        "--model",
        default=ACTIVE_PREREGISTRATION.model,
        help="Inspect model id; defaults to the active pre-registered model",
    )
    return parser


def _print_dry_run(specs: list[RunSpec], budget_usd: float) -> None:
    per_run_cost = _estimate_cost_usd(_DRY_RUN_TOKENS_INPUT, _DRY_RUN_TOKENS_OUTPUT)
    total = per_run_cost * len(specs)
    sys.stdout.write(
        f"dry-run: {len(specs)} runs enumerated\n"
        f"  estimated per-run cost: ${per_run_cost:.4f} "
        f"({_DRY_RUN_TOKENS_INPUT} in / {_DRY_RUN_TOKENS_OUTPUT} out tokens @ "
        f"${_PRICE_INPUT_USD_PER_MTOK}/MTok in, ${_PRICE_OUTPUT_USD_PER_MTOK}/MTok out)\n"
        f"  estimated total cost:    ${total:.2f} (budget ${budget_usd:.2f})\n"
    )
    # Compact enumeration listing — useful when piping into less.
    for spec in specs:
        sys.stdout.write(f"  - {spec.scenario_id} {spec.rung} seed={spec.seed}\n")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    scenarios = _parse_scenarios_arg(args.scenarios, args.scenarios_dir)
    rungs = _parse_rungs_arg(args.rungs)
    specs = enumerate_runs(scenarios, rungs, args.seeds)
    if args.dry_run:
        _print_dry_run(specs, args.budget_usd)
        return 0
    # token_limit covers total task budget — args.max_tokens is the
    # per-response cap; multiplier of 20 covers ~20 tool-call rounds, which
    # comfortably brackets every scenario in the suite at the time of
    # writing. Tune this if Inspect's token_limit semantics shift or if
    # scenarios grow past ~20 turns.
    token_limit = args.max_tokens * 20 if args.max_tokens else None
    time_limit = args.max_task_time_s if args.max_task_time_s else None
    results = run_sweep(
        specs,
        model=args.model,
        budget_usd=args.budget_usd,
        token_limit=token_limit,
        time_limit=time_limit,
    )
    write_parquet(results, args.output)
    passed = sum(1 for r in results if r.score == 1.0)
    failed = sum(1 for r in results if r.score == 0.0)
    aborted = sum(1 for r in results if "budget exceeded" in r.error_msg)
    errored = sum(1 for r in results if r.error_msg and "budget exceeded" not in r.error_msg)
    total_cost = sum(r.cost_usd for r in results)
    sys.stdout.write(
        f"sweep complete: {len(results)} runs ({passed} pass, {failed} fail, "
        f"{errored} error, {aborted} aborted)\n"
        f"  cumulative cost: ${total_cost:.2f} (budget ${args.budget_usd:.2f})\n"
        f"  parquet: {args.output}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
