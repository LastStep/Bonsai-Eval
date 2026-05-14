"""Unit tests for `scripts/run_validation.py` (Plan 38 §P2.5 readiness).

No live `inspect_ai.eval` invocation — `_invoke_eval` is monkeypatched
to return synthetic `EvalOutcome` values immediately. The tests verify:

  - Dry-run enumerates the cartesian product correctly.
  - `--scenarios` / `--rungs` filters narrow the product as documented.
  - Parquet schema + dtype round-trip via duckdb.
  - Budget abort writes a partial parquet with explicit aborted-row markers.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from scripts import run_validation as rv

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = REPO_ROOT / "scenarios" / "bonsai_behavioral"


# --- enumeration / argparse smoke tests -----------------------------------


def test_dry_run_enumeration_count(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Defaults: 12 scenarios × 3 rungs × 3 seeds = 108 runs."""
    rc = rv.main(
        [
            "--dry-run",
            "--output",
            str(tmp_path / "ignored.parquet"),
            "--scenarios-dir",
            str(SCENARIOS_DIR),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "108 runs enumerated" in captured, captured


def test_dry_run_scenario_filter(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """`--scenarios A,B` over default rungs/seeds = 2 × 3 × 3 = 18 runs."""
    a, b = sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))[:2]
    rc = rv.main(
        [
            "--dry-run",
            "--scenarios",
            f"{a},{b}",
            "--output",
            str(tmp_path / "ignored.parquet"),
            "--scenarios-dir",
            str(SCENARIOS_DIR),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "18 runs enumerated" in captured, captured


def test_dry_run_rung_filter(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """`--rungs r1` = 12 × 1 × 3 = 36 runs."""
    rc = rv.main(
        [
            "--dry-run",
            "--rungs",
            "r1",
            "--output",
            str(tmp_path / "ignored.parquet"),
            "--scenarios-dir",
            str(SCENARIOS_DIR),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "36 runs enumerated" in captured, captured


def test_dry_run_single_combo(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """`--scenarios X --rungs r2 --seeds 1` = 1 run."""
    pick = sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))[0]
    rc = rv.main(
        [
            "--dry-run",
            "--scenarios",
            pick,
            "--rungs",
            "r2",
            "--seeds",
            "1",
            "--output",
            str(tmp_path / "ignored.parquet"),
            "--scenarios-dir",
            str(SCENARIOS_DIR),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "1 runs enumerated" in captured, captured


def test_unknown_rung_token_rejected(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        rv.main(
            [
                "--dry-run",
                "--rungs",
                "r9",
                "--output",
                str(tmp_path / "ignored.parquet"),
                "--scenarios-dir",
                str(SCENARIOS_DIR),
            ]
        )


def test_unknown_scenario_rejected(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        rv.main(
            [
                "--dry-run",
                "--scenarios",
                "does-not-exist",
                "--output",
                str(tmp_path / "ignored.parquet"),
                "--scenarios-dir",
                str(SCENARIOS_DIR),
            ]
        )


def test_enumerate_runs_order_is_stable() -> None:
    """Cartesian product is emitted in (scenario, rung, seed) order."""
    specs = rv.enumerate_runs(["a", "b"], ["rung1", "rung2"], 2)
    assert [(s.scenario_id, s.rung, s.seed) for s in specs] == [
        ("a", "rung1", 0),
        ("a", "rung1", 1),
        ("a", "rung2", 0),
        ("a", "rung2", 1),
        ("b", "rung1", 0),
        ("b", "rung1", 1),
        ("b", "rung2", 0),
        ("b", "rung2", 1),
    ]


# --- parquet schema test ---------------------------------------------------


def test_parquet_schema(tmp_path: Path) -> None:
    """Schema columns + dtypes survive a parquet round-trip via duckdb."""
    results = [
        rv.RunResult(
            scenario_id="a",
            rung="rung1",
            seed=0,
            score=1.0,
            evaluator_details='[{"check": "x", "passed": true}]',
            cost_usd=0.0125,
            duration_s=4.2,
            error_msg="",
            log_path="/tmp/log.eval",
        ),
        rv.RunResult(
            scenario_id="a",
            rung="rung2",
            seed=0,
            score=0.0,
            evaluator_details="[]",
            cost_usd=0.03,
            duration_s=5.7,
            error_msg="oops",
            log_path="",
        ),
    ]
    out = tmp_path / "p2-validation.parquet"
    rv.write_parquet(results, out)
    assert out.exists()

    cols = duckdb.sql(f"SELECT * FROM read_parquet('{out}')").df()
    assert list(cols.columns) == [
        "scenario_id",
        "rung",
        "seed",
        "score",
        "evaluator_details",
        "cost_usd",
        "duration_s",
        "error_msg",
        "log_path",
    ]
    assert len(cols) == 2
    # Type sanity: ids are object/str (pandas may surface as StringDtype
    # under recent pyarrow), score / cost / duration are floats, seed is
    # integer. We check via `is_string_dtype` / dtype.kind for the
    # numerics so the assertion survives pandas' string-dtype evolution.
    import pandas as _pd  # noqa: PLC0415

    assert _pd.api.types.is_string_dtype(cols["scenario_id"]) or cols["scenario_id"].dtype == object
    assert _pd.api.types.is_string_dtype(cols["rung"]) or cols["rung"].dtype == object
    assert cols["seed"].dtype.kind in {"i", "u"}
    assert cols["score"].dtype.kind == "f"
    assert cols["cost_usd"].dtype.kind == "f"
    assert cols["duration_s"].dtype.kind == "f"


# --- budget abort path -----------------------------------------------------


def test_budget_abort_writes_partial_parquet(tmp_path: Path) -> None:
    """When cost crosses the budget mid-sweep, tail rows are marked aborted."""
    specs = rv.enumerate_runs(["a", "b", "c"], ["rung1"], 1)  # 3 specs total

    # Synthetic invoker: every run costs $5; budget is $7. The first run
    # consumes $5 (under budget), the second pushes cumulative to $10 (over).
    # The third run must be emitted as `RunResult.aborted`.
    def fake_invoker(spec: rv.RunSpec, model: str, **kwargs: object) -> rv.EvalOutcome:
        del spec, model, kwargs
        return rv.EvalOutcome(
            score=1.0,
            evaluator_details=[],
            input_tokens=5_000_000,  # $5 input @ $1/MTok
            output_tokens=0,
            duration_s=1.0,
        )

    results = rv.run_sweep(
        specs, model="anthropic/claude-haiku-4-5", budget_usd=7.0, eval_invoker=fake_invoker
    )
    assert len(results) == 3
    # First two ran; third is aborted.
    assert results[0].error_msg == ""
    assert results[0].cost_usd == pytest.approx(5.0)
    assert results[1].error_msg == ""
    assert results[1].cost_usd == pytest.approx(5.0)
    assert "budget exceeded" in results[2].error_msg
    assert results[2].cost_usd == 0.0

    out = tmp_path / "abort.parquet"
    rv.write_parquet(results, out)
    df = duckdb.sql(f"SELECT * FROM read_parquet('{out}') ORDER BY scenario_id").df()
    assert len(df) == 3
    aborted_row = df[df["scenario_id"] == "c"].iloc[0]
    assert "budget exceeded" in aborted_row["error_msg"]


def test_run_sweep_records_invoker_exception(tmp_path: Path) -> None:
    """A raising invoker yields an `errored` row, not a crash."""
    del tmp_path
    specs = rv.enumerate_runs(["a"], ["rung1"], 1)

    def broken_invoker(spec: rv.RunSpec, model: str, **kwargs: object) -> rv.EvalOutcome:
        del spec, model, kwargs
        raise RuntimeError("synthetic boom")

    results = rv.run_sweep(specs, model="x", budget_usd=20.0, eval_invoker=broken_invoker)
    assert len(results) == 1
    assert "RuntimeError" in results[0].error_msg
    assert "synthetic boom" in results[0].error_msg


# --- cost-estimate purity --------------------------------------------------


def test_cost_estimate_is_deterministic() -> None:
    """`_estimate_cost_usd` is a pure function of input/output tokens."""
    assert rv._estimate_cost_usd(0, 0) == 0.0
    # 1M input + 1M output @ $1 / $5 per MTok = $6.
    assert rv._estimate_cost_usd(1_000_000, 1_000_000) == pytest.approx(6.0)


# --- run-spec path uniqueness ----------------------------------------------


def test_run_spec_home_dir_is_unique_per_combo() -> None:
    """Distinct (scenario, rung, seed) → distinct home/workspace paths."""
    a = rv.RunSpec(scenario_id="x", rung="rung2", seed=0)
    b = rv.RunSpec(scenario_id="x", rung="rung2", seed=1)
    c = rv.RunSpec(scenario_id="x", rung="rung3", seed=0)
    d = rv.RunSpec(scenario_id="y", rung="rung2", seed=0)
    homes = {a.home_dir, b.home_dir, c.home_dir, d.home_dir}
    workspaces = {a.workspace_dir, b.workspace_dir, c.workspace_dir, d.workspace_dir}
    assert len(homes) == 4
    assert len(workspaces) == 4


# --- monkeypatched invoker via main() smoke test --------------------------


def test_main_executes_with_synthetic_invoker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end smoke: main() with a single-combo argv writes parquet."""
    pick = sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))[0]
    out = tmp_path / "smoke.parquet"

    def fake_invoker(spec: rv.RunSpec, model: str, **kwargs: object) -> rv.EvalOutcome:
        del spec, model, kwargs
        return rv.EvalOutcome(
            score=1.0,
            evaluator_details=[{"check": "smoke", "passed": True}],
            input_tokens=1000,
            output_tokens=500,
            duration_s=0.5,
        )

    monkeypatch.setattr(rv, "_invoke_eval", fake_invoker)
    rc = rv.main(
        [
            "--scenarios",
            pick,
            "--rungs",
            "r2",
            "--seeds",
            "1",
            "--output",
            str(out),
            "--scenarios-dir",
            str(SCENARIOS_DIR),
        ]
    )
    assert rc == 0
    assert out.exists()
    captured = capsys.readouterr().out
    assert "sweep complete: 1 runs" in captured, captured

    df = duckdb.sql(f"SELECT * FROM read_parquet('{out}')").df()
    assert len(df) == 1
    assert df.iloc[0]["score"] == 1.0


# --- budget-knob forwarding -----------------------------------------------


def test_invoker_receives_budget_kwargs() -> None:
    """`run_sweep` must forward token_limit/time_limit/cost_limit into invoker."""
    captured: list[dict[str, object]] = []

    def recording_invoker(spec: rv.RunSpec, model: str, **kwargs: object) -> rv.EvalOutcome:
        del spec, model
        captured.append(dict(kwargs))
        return rv.EvalOutcome(score=1.0, input_tokens=0, output_tokens=0)

    specs = rv.enumerate_runs(["a"], ["rung1"], 1)
    rv.run_sweep(
        specs,
        model="x",
        budget_usd=20.0,
        token_limit=163_840,  # 8192 * 20
        time_limit=600,
        eval_invoker=recording_invoker,
    )
    assert len(captured) == 1
    kwargs = captured[0]
    assert kwargs.get("token_limit") == 163_840
    assert kwargs.get("time_limit") == 600
    # cost_limit must be the remaining budget envelope (first run = full
    # budget since cumulative_cost is 0).
    assert kwargs.get("cost_limit") == pytest.approx(20.0)


def test_invoker_omits_unset_budget_kwargs() -> None:
    """When `_invoke_eval` callers leave `token_limit`/`time_limit` as None,
    the kwarg is passed through as None — the actual `inspect_eval` call
    inside `_invoke_eval` then drops None keys. The contract at the
    invoker boundary is: knobs always present (None means unset).
    """
    captured: list[dict[str, object]] = []

    def recording_invoker(spec: rv.RunSpec, model: str, **kwargs: object) -> rv.EvalOutcome:
        del spec, model
        captured.append(dict(kwargs))
        return rv.EvalOutcome(score=1.0, input_tokens=0, output_tokens=0)

    specs = rv.enumerate_runs(["a"], ["rung1"], 1)
    rv.run_sweep(
        specs,
        model="x",
        budget_usd=20.0,
        eval_invoker=recording_invoker,
        # token_limit + time_limit deliberately omitted
    )
    assert captured[0].get("token_limit") is None
    assert captured[0].get("time_limit") is None


def test_invoke_eval_drops_unset_kwargs_from_inspect_eval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_invoke_eval` MUST NOT leak `token_limit=None` / `time_limit=None`
    into `inspect_ai.eval()` when the caller leaves them unset.

    This pins the "default behavior preserved" contract: callers that
    don't opt into budget caps see the same `inspect_eval(task, model=...)`
    call shape as the pre-amend implementation.
    """
    # Pick the first real scenario id so `_invoke_eval`'s task-fn lookup
    # succeeds — we monkeypatch the eval call to capture kwargs.
    pick = sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))[0]

    captured: dict[str, object] = {}

    def fake_inspect_eval(task: object, **kwargs: object) -> list[object]:
        captured.update(kwargs)
        captured["_task"] = task
        # Return [] so `_invoke_eval` short-circuits with "no logs"
        # error_msg — we don't care about the post-call path here.
        return []

    # Monkeypatch the lazy import target. `_invoke_eval` does
    # `from inspect_ai import eval as inspect_eval` inside the function,
    # so we patch `inspect_ai.eval` at the module level.
    import inspect_ai

    monkeypatch.setattr(inspect_ai, "eval", fake_inspect_eval)

    spec = rv.RunSpec(scenario_id=pick, rung="rung2", seed=0)
    outcome = rv._invoke_eval(spec, model="anthropic/claude-haiku-4-5")
    # No knobs forwarded → kwargs has model only.
    assert "token_limit" not in captured
    assert "time_limit" not in captured
    assert "cost_limit" not in captured
    assert captured.get("model") == "anthropic/claude-haiku-4-5"
    # Sanity: we hit the "no logs" branch.
    assert "no logs" in outcome.error_msg


def test_invoke_eval_forwards_set_kwargs_to_inspect_eval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a caller sets `token_limit`/`time_limit`/`cost_limit`, the
    values reach `inspect_ai.eval()` verbatim.
    """
    pick = sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))[0]

    captured: dict[str, object] = {}

    def fake_inspect_eval(task: object, **kwargs: object) -> list[object]:
        captured.update(kwargs)
        return []

    import inspect_ai

    monkeypatch.setattr(inspect_ai, "eval", fake_inspect_eval)

    spec = rv.RunSpec(scenario_id=pick, rung="rung2", seed=0)
    rv._invoke_eval(
        spec,
        model="anthropic/claude-haiku-4-5",
        token_limit=163_840,
        time_limit=600,
        cost_limit=15.0,
    )
    assert captured.get("token_limit") == 163_840
    assert captured.get("time_limit") == 600
    assert captured.get("cost_limit") == 15.0


def test_run_sweep_per_run_cost_limit_shrinks_with_cumulative_cost() -> None:
    """`cost_limit` forwarded to each run = remaining budget envelope.

    Run 1 sees the full $20; run 2 sees ($20 - cost_of_run_1); etc.
    Once remaining hits 0, `cost_limit` is forwarded as None and the
    post-hoc abort path takes over.
    """
    captured: list[float | None] = []

    def recording_invoker(spec: rv.RunSpec, model: str, **kwargs: object) -> rv.EvalOutcome:
        del spec, model
        captured.append(kwargs.get("cost_limit"))  # type: ignore[arg-type]
        # Each run costs $5 (5M input tokens @ $1/MTok).
        return rv.EvalOutcome(score=1.0, input_tokens=5_000_000, output_tokens=0)

    specs = rv.enumerate_runs(["a", "b", "c"], ["rung1"], 1)
    rv.run_sweep(
        specs,
        model="x",
        budget_usd=20.0,
        eval_invoker=recording_invoker,
    )
    # Run 1 sees $20 remaining; run 2 sees $15; run 3 sees $10.
    assert captured == [pytest.approx(20.0), pytest.approx(15.0), pytest.approx(10.0)]


# --- valid-rung guard reflects bonsai_behavioral.py contract -------------


def test_rung_token_to_name_alignment() -> None:
    """The CLI's `r1/r2/r3` tokens must map onto the task layer's rung names."""
    from bonsai_eval.tasks.bonsai_behavioral import VALID_RUNGS  # noqa: PLC0415

    assert set(rv.RUNG_TOKEN_TO_NAME.values()) == VALID_RUNGS


# --- Haiku 4.5 cost registration (Inspect AI cost_limit gate) -------------


def test_ensure_haiku_cost_registered_called_once_across_invocations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_invoke_eval` must register Haiku 4.5 pricing with Inspect AI's
    model-info DB exactly once per process so `cost_limit=` does not trip
    the PrerequisiteError pre-flight check.

    Two `_invoke_eval` calls should result in a single `set_model_cost`
    invocation; the args must match the Haiku 4.5 list pricing constants.
    """
    pick = sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))[0]

    # Reset the module-level guard so this test is order-independent.
    monkeypatch.setattr(rv, "_haiku_cost_registered", False)

    recorded: list[tuple[object, object]] = []

    def recording_set_model_cost(model_id: object, cost: object) -> None:
        recorded.append((model_id, cost))

    # No-op inspect_ai.eval so `_invoke_eval` short-circuits with "no logs"
    # without spending real money or hitting the network.
    def fake_inspect_eval(task: object, **kwargs: object) -> list[object]:
        del task, kwargs
        return []

    import inspect_ai
    from inspect_ai.model import _model_info as model_info_mod

    monkeypatch.setattr(inspect_ai, "eval", fake_inspect_eval)
    monkeypatch.setattr(model_info_mod, "set_model_cost", recording_set_model_cost)

    spec = rv.RunSpec(scenario_id=pick, rung="rung2", seed=0)
    rv._invoke_eval(spec, model="anthropic/claude-haiku-4-5")
    rv._invoke_eval(spec, model="anthropic/claude-haiku-4-5")

    assert len(recorded) == 1, f"expected exactly one set_model_cost call, got {len(recorded)}"
    model_id, cost = recorded[0]
    assert model_id == "anthropic/claude-haiku-4-5"
    assert cost.input == 1.00
    assert cost.output == 5.00
    assert cost.input_cache_read == 0.10
    assert cost.input_cache_write == 1.25
