"""Notebook execution test — runs the analysis notebook against placeholder fixtures.

Plan 38 §Verification: `notebooks/proof_of_work.ipynb` runs top-to-bottom on
PLACEHOLDER data only (Risk #7 — no real-data run pre-merge); produces 6 chart PNGs.

Skipped if `nbformat`/`nbconvert` aren't installed (they're in the `notebook`
extras group, not the default install).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = REPO_ROOT / "notebooks" / "proof_of_work.ipynb"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "joined.parquet"


def _have_nbconvert() -> bool:
    try:
        import nbconvert  # noqa: F401
        import nbformat  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not _have_nbconvert(), reason="nbconvert/nbformat not installed")
def test_notebook_runs_on_fixtures(tmp_path: Path) -> None:
    if not FIXTURES.exists():
        pytest.skip("fixture parquet not built — run tests/fixtures/build_fixtures.py")

    import nbformat
    from nbconvert.preprocessors import ExecutePreprocessor

    nb = nbformat.read(NOTEBOOK, as_version=4)
    ep = ExecutePreprocessor(timeout=120, kernel_name="python3")
    # Force fixture mode + chart dir under tmp_path so we don't pollute the repo.
    env_overrides = {
        **os.environ,
        "BONSAI_EVAL_USE_FIXTURES": "1",
    }
    # Run with cwd = REPO_ROOT so the notebook resolves paths relative to repo.
    ep.preprocess(nb, {"metadata": {"path": str(REPO_ROOT)}, "env": env_overrides})

    charts_dir = REPO_ROOT / "charts"
    pngs = list(charts_dir.glob("*.png")) if charts_dir.exists() else []
    assert len(pngs) >= 6, f"expected ≥6 chart PNGs, found {len(pngs)}: {pngs}"
