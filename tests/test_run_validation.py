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
    def fake_invoker(spec: rv.RunSpec, model: str) -> rv.EvalOutcome:
        del spec, model
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

    def broken_invoker(spec: rv.RunSpec, model: str) -> rv.EvalOutcome:
        del spec, model
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

    def fake_invoker(spec: rv.RunSpec, model: str) -> rv.EvalOutcome:
        del spec, model
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


# --- valid-rung guard reflects bonsai_behavioral.py contract -------------


def test_rung_token_to_name_alignment() -> None:
    """The CLI's `r1/r2/r3` tokens must map onto the task layer's rung names."""
    from bonsai_eval.tasks.bonsai_behavioral import VALID_RUNGS  # noqa: PLC0415

    assert set(rv.RUNG_TOKEN_TO_NAME.values()) == VALID_RUNGS
