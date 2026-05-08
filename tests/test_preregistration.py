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
        )


def test_violation_for_non_config_input() -> None:
    with pytest.raises(PreregistrationViolation, match="Expected"):
        assert_preregistration("not a config", ACTIVE_PREREGISTRATION)  # type: ignore[arg-type]
