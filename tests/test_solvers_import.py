"""Solver-importability + pre-reg-assertion tests — non-API.

Verifies all 3 rung factories are importable from `bonsai_eval.solvers` and
that they enforce the pre-registration assertion at entry. Does NOT actually
construct the underlying agents (that requires `inspect-swe` to spin up an
ACP transport — out of scope for non-API tests).
"""

from __future__ import annotations

import dataclasses

import pytest

from bonsai_eval.preregistration import (
    ACTIVE_PREREGISTRATION,
    PreregistrationViolation,
)


def test_rung_factories_importable() -> None:
    from bonsai_eval.solvers import rung1_raw_api, rung2_bare_cc, rung3_bonsai

    assert callable(rung1_raw_api)
    assert callable(rung2_bare_cc)
    assert callable(rung3_bonsai)


def test_rung_factories_in_all() -> None:
    import bonsai_eval.solvers as solvers

    assert "rung1_raw_api" in solvers.__all__
    assert "rung2_bare_cc" in solvers.__all__
    assert "rung3_bonsai" in solvers.__all__


def test_rung1_raw_api_rejects_mismatched_preregistration() -> None:
    """Smoke test the assertion path without spinning up an agent.

    We import the validator directly rather than calling the factory (which
    would try to construct a real `mini_swe_agent`). This tests the contract
    described in Plan 38 §P0.3: a caller who passes a non-matching pre-reg
    config gets a `PreregistrationViolation` before any agent work happens.
    """
    from bonsai_eval.solvers.rungs import _validate_preregistration

    bad = dataclasses.replace(ACTIVE_PREREGISTRATION, temperature=0.7)
    with pytest.raises(PreregistrationViolation):
        _validate_preregistration(bad)


def test_rung_validator_accepts_active_config() -> None:
    from bonsai_eval.solvers.rungs import _validate_preregistration

    # Default (None) should resolve to ACTIVE_PREREGISTRATION.
    assert _validate_preregistration(None) is ACTIVE_PREREGISTRATION
    # Explicit pass of ACTIVE_PREREGISTRATION should also pass.
    assert _validate_preregistration(ACTIVE_PREREGISTRATION) is ACTIVE_PREREGISTRATION


def test_rung3_rejects_missing_bonsai_config(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """rung3_bonsai validates the config path before trying to spawn anything."""
    from bonsai_eval.solvers import rung3_bonsai

    missing = tmp_path / "does-not-exist.bonsai.yaml"
    with pytest.raises(FileNotFoundError, match="bonsai_config"):
        rung3_bonsai(bonsai_config=missing)
