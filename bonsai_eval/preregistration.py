"""Pre-registration config — the locked-at-claim-merge knobs we promise not to vary.

Plan 38 §"Pre-Registration" + §P0.3 require that every benchmark run pass the same
model / temperature / max_tokens / allowed_tools / judge_model / judge_prompt_hash.
This module defines a frozen dataclass plus an assertion helper used at every
solver entry point. If a caller tries to override a pinned field, we raise.

Methodology rationale (from online research, 2026-05-07):
- Reward-hacking demonstrated at scale (Berkeley Apr 2026) — same model+tools across rungs.
- Style/length bias dominates judge deltas under 5pts — same judge model + prompt hash.
- HAL-style cross-agent comparisons require pinned tool list — `allowed_tools` is a frozenset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Any


class PreregistrationViolation(RuntimeError):
    """Raised when a solver invocation does not match the active pre-registered config."""


# PEP 440 / semver-ish: `MAJOR.MINOR.PATCH` with optional `-pre` or `+build` suffix.
# We intentionally keep this permissive — the goal is "machine-checkable shape",
# not full PEP 440 grammar. Drift detection comes from string-equality elsewhere.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+].+)?$")


@dataclass(frozen=True, slots=True)
class PreregistrationConfig:
    """Frozen config — every field is part of the pre-registration commitment.

    Two `PreregistrationConfig` instances compare equal iff every field matches.
    Fields use immutable types (`str`, `int`, `float`, `frozenset`) so the
    `frozen=True` guarantee survives nested mutation attempts.

    Field order (positional callers beware — kwargs are the supported pattern):
        1. model
        2. temperature
        3. max_tokens
        4. allowed_tools
        5. judge_model
        6. judge_prompt_sha256
        7. mini_swe_agent_version  (rung-1 CLI semver, e.g. "2.2.3")
        8. inspect_swe_version     (inspect-swe package semver, e.g. "0.2.51")
    """

    model: str
    temperature: float
    max_tokens: int
    allowed_tools: frozenset[str]
    judge_model: str
    judge_prompt_sha256: str
    mini_swe_agent_version: str
    inspect_swe_version: str

    def __post_init__(self) -> None:
        # Defensive type-narrowing — a caller passing a `set` instead of `frozenset`
        # would defeat the freeze. Auto-convert for ergonomics, then assert.
        if not isinstance(self.allowed_tools, frozenset):
            object.__setattr__(self, "allowed_tools", frozenset(self.allowed_tools))
        if len(self.judge_prompt_sha256) != 64:
            raise ValueError(
                f"judge_prompt_sha256 must be a 64-char hex digest, "
                f"got {len(self.judge_prompt_sha256)} chars"
            )
        if self.temperature < 0 or self.temperature > 2:
            raise ValueError(f"temperature out of range: {self.temperature}")
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive: {self.max_tokens}")
        if not _VERSION_RE.match(self.mini_swe_agent_version):
            raise ValueError(
                f"mini_swe_agent_version must be PEP 440 / semver-shaped "
                f"(MAJOR.MINOR.PATCH[-pre|+build]), got {self.mini_swe_agent_version!r}"
            )
        if not _VERSION_RE.match(self.inspect_swe_version):
            raise ValueError(
                f"inspect_swe_version must be PEP 440 / semver-shaped "
                f"(MAJOR.MINOR.PATCH[-pre|+build]), got {self.inspect_swe_version!r}"
            )


def assert_preregistration(cfg: PreregistrationConfig, expected: PreregistrationConfig) -> None:
    """Assert `cfg` matches `expected` field-by-field, or raise `PreregistrationViolation`.

    Field-by-field comparison gives the caller a precise error message naming the
    mismatched field — better debugging than a one-shot equality check.
    """
    if not isinstance(cfg, PreregistrationConfig):
        raise PreregistrationViolation(f"Expected PreregistrationConfig, got {type(cfg).__name__}")
    if not isinstance(expected, PreregistrationConfig):
        raise PreregistrationViolation(
            f"Expected PreregistrationConfig, got {type(expected).__name__}"
        )
    mismatches: list[str] = []
    for field in fields(cfg):
        actual: Any = getattr(cfg, field.name)
        want: Any = getattr(expected, field.name)
        if actual != want:
            mismatches.append(f"  {field.name}: got {actual!r}, expected {want!r}")
    if mismatches:
        raise PreregistrationViolation(
            "Pre-registration violation — fields do not match the locked claim:\n"
            + "\n".join(mismatches)
        )


# --- Active claim's locked values ---
# Update this only when a new claim is opened. Changing it mid-measurement breaks
# the pre-registration commitment. The judge_prompt_sha256 placeholder will be
# replaced once the judge prompt template is finalized in P2 — until then, the
# value below is the SHA-256 of the literal string "PLACEHOLDER_JUDGE_PROMPT_V0"
# so the assertion plumbing is testable.
_PLACEHOLDER_JUDGE_PROMPT_SHA256 = (
    # python -c "import hashlib; print(hashlib.sha256(b'PLACEHOLDER_JUDGE_PROMPT_V0').hexdigest())"
    "f5fe124dae5acb3a5e9bbff764738eb3d0be55a86b4cd585e2c4b476eada6cc3"
)

ACTIVE_PREREGISTRATION = PreregistrationConfig(
    model="anthropic/claude-haiku-4-5",
    temperature=0.0,
    max_tokens=8192,
    allowed_tools=frozenset({"Bash", "Read", "Edit", "Write", "Glob", "Grep"}),
    judge_model="anthropic/claude-haiku-4-5",
    judge_prompt_sha256=_PLACEHOLDER_JUDGE_PROMPT_SHA256,
    # Solver-stack version pins — must equal the constants in
    # `bonsai_eval.solvers.rungs`. Drift between these two locations is
    # machine-enforced by `_validate_versions_match_preregistration`.
    mini_swe_agent_version="2.2.3",
    inspect_swe_version="0.2.51",
)
