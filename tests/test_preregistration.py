"""Pre-registration assertion tests — Plan 38 §P0.3.

Verifies the frozen-dataclass + assertion machinery in
`bonsai_eval.preregistration` is sound. No API calls.
"""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from bonsai_eval.preregistration import (
    ACTIVE_PREREGISTRATION,
    PreregistrationConfig,
    PreregistrationViolation,
    assert_preregistration,
)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_active_config_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        ACTIVE_PREREGISTRATION.model = "anthropic/claude-opus-4-7"  # type: ignore[misc]


def test_active_config_self_consistent() -> None:
    # Trivially: ACTIVE_PREREGISTRATION matches itself.
    assert_preregistration(ACTIVE_PREREGISTRATION, ACTIVE_PREREGISTRATION)


def test_assert_preregistration_catches_model_mismatch() -> None:
    bad = dataclasses.replace(ACTIVE_PREREGISTRATION, model="anthropic/claude-opus-4-7")
    with pytest.raises(PreregistrationViolation, match="model"):
        assert_preregistration(bad, ACTIVE_PREREGISTRATION)


def test_assert_preregistration_catches_temp_mismatch() -> None:
    bad = dataclasses.replace(ACTIVE_PREREGISTRATION, temperature=0.7)
    with pytest.raises(PreregistrationViolation, match="temperature"):
        assert_preregistration(bad, ACTIVE_PREREGISTRATION)


def test_assert_preregistration_catches_tools_mismatch() -> None:
    bad = dataclasses.replace(
        ACTIVE_PREREGISTRATION,
        allowed_tools=frozenset({"Bash"}),  # missing the rest
    )
    with pytest.raises(PreregistrationViolation, match="allowed_tools"):
        assert_preregistration(bad, ACTIVE_PREREGISTRATION)


def test_assert_preregistration_catches_judge_hash_mismatch() -> None:
    bad = dataclasses.replace(ACTIVE_PREREGISTRATION, judge_prompt_sha256=_hash("DIFFERENT_PROMPT"))
    with pytest.raises(PreregistrationViolation, match="judge_prompt_sha256"):
        assert_preregistration(bad, ACTIVE_PREREGISTRATION)


def test_set_is_coerced_to_frozenset() -> None:
    cfg = PreregistrationConfig(
        model="anthropic/claude-haiku-4-5",
        temperature=0.0,
        max_tokens=4096,
        allowed_tools={"Bash", "Read"},  # type: ignore[arg-type]  # set, not frozenset
        judge_model="anthropic/claude-haiku-4-5",
        judge_prompt_sha256=_hash("any"),
        mini_swe_agent_version="2.2.3",
        inspect_swe_version="0.2.51",
    )
    assert isinstance(cfg.allowed_tools, frozenset)


def test_short_hash_rejected() -> None:
    with pytest.raises(ValueError, match="64-char hex"):
        PreregistrationConfig(
            model="m",
            temperature=0.0,
            max_tokens=1,
            allowed_tools=frozenset(),
            judge_model="m",
            judge_prompt_sha256="too-short",
            mini_swe_agent_version="2.2.3",
            inspect_swe_version="0.2.51",
        )


def test_negative_temperature_rejected() -> None:
    with pytest.raises(ValueError, match="temperature"):
        PreregistrationConfig(
            model="m",
            temperature=-0.1,
            max_tokens=1,
            allowed_tools=frozenset(),
            judge_model="m",
            judge_prompt_sha256=_hash("x"),
            mini_swe_agent_version="2.2.3",
            inspect_swe_version="0.2.51",
        )


def test_zero_max_tokens_rejected() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        PreregistrationConfig(
            model="m",
            temperature=0.0,
            max_tokens=0,
            allowed_tools=frozenset(),
            judge_model="m",
            judge_prompt_sha256=_hash("x"),
            mini_swe_agent_version="2.2.3",
            inspect_swe_version="0.2.51",
        )


def test_violation_for_non_config_input() -> None:
    with pytest.raises(PreregistrationViolation, match="Expected"):
        assert_preregistration("not a config", ACTIVE_PREREGISTRATION)  # type: ignore[arg-type]


# --- Solver-stack version fields (Plan 38 §"Pre-Registration" + §P0.3) ---


def test_valid_construction_with_version_fields() -> None:
    cfg = PreregistrationConfig(
        model="m",
        temperature=0.0,
        max_tokens=1,
        allowed_tools=frozenset(),
        judge_model="m",
        judge_prompt_sha256=_hash("x"),
        mini_swe_agent_version="2.2.3",
        inspect_swe_version="0.2.51",
    )
    assert cfg.mini_swe_agent_version == "2.2.3"
    assert cfg.inspect_swe_version == "0.2.51"


def test_invalid_mini_swe_agent_version_rejected() -> None:
    with pytest.raises(ValueError, match="mini_swe_agent_version"):
        PreregistrationConfig(
            model="m",
            temperature=0.0,
            max_tokens=1,
            allowed_tools=frozenset(),
            judge_model="m",
            judge_prompt_sha256=_hash("x"),
            mini_swe_agent_version="not-a-version",
            inspect_swe_version="0.2.51",
        )


def test_invalid_inspect_swe_version_rejected() -> None:
    with pytest.raises(ValueError, match="inspect_swe_version"):
        PreregistrationConfig(
            model="m",
            temperature=0.0,
            max_tokens=1,
            allowed_tools=frozenset(),
            judge_model="m",
            judge_prompt_sha256=_hash("x"),
            mini_swe_agent_version="2.2.3",
            inspect_swe_version="garbage",
        )


def test_version_with_prerelease_suffix_accepted() -> None:
    # Plan 38 — regex is `^\d+\.\d+\.\d+(?:[-+].+)?$`, so pre/build suffixes ok.
    cfg = PreregistrationConfig(
        model="m",
        temperature=0.0,
        max_tokens=1,
        allowed_tools=frozenset(),
        judge_model="m",
        judge_prompt_sha256=_hash("x"),
        mini_swe_agent_version="2.2.3-rc1",
        inspect_swe_version="0.2.51+build42",
    )
    assert cfg.mini_swe_agent_version == "2.2.3-rc1"
    assert cfg.inspect_swe_version == "0.2.51+build42"


def test_active_preregistration_pins_solver_stack_versions() -> None:
    # Guards against silent drift in the locked config. If these change you
    # are amending the claim — make sure the rung constants move in lockstep.
    assert ACTIVE_PREREGISTRATION.mini_swe_agent_version == "2.2.3"
    assert ACTIVE_PREREGISTRATION.inspect_swe_version == "0.2.51"


def test_rung_entry_points_detect_mini_swe_agent_version_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Flip the rung-1 constant without touching the pre-reg claim — every
    # rung's entry point should refuse to build a solver.
    from bonsai_eval.solvers import rungs

    monkeypatch.setattr(rungs, "MINI_SWE_AGENT_VERSION", "9.9.9")
    with pytest.raises(PreregistrationViolation, match="MINI_SWE_AGENT_VERSION"):
        rungs.rung1_raw_api()


def test_rung_entry_points_detect_inspect_swe_version_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    from bonsai_eval.solvers import rungs

    monkeypatch.setattr(rungs, "INSPECT_SWE_VERSION_PIN", "9.9.9")
    # rung2 requires home_dir, but version validation runs first — so we pass
    # a dummy path and still expect the drift error before that check fires.
    with pytest.raises(PreregistrationViolation, match="INSPECT_SWE_VERSION_PIN"):
        rungs.rung2_bare_cc(home_dir=tmp_path)  # type: ignore[arg-type]
