"""Inspect AI substrate smoke tests — Plan 38 §P0.2.

All 3 cases require `ANTHROPIC_API_KEY` and incur paid API calls (target:
< $0.10 total). They are marked `@pytest.mark.requires_api` and SKIPPED in
default `make test` runs. Run via `make test-api` once a key is available.

Cost guardrail per dispatch: any single test > $0.03 is a smell — stop and
investigate token usage rather than papering over the symptom.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.log import EvalLog
from inspect_ai.scorer import includes
from inspect_ai.solver import generate

from bonsai_eval.solvers.rungs import rung1_raw_api, rung2_bare_cc

# All tests in this module hit the API.
# We also suppress `ResourceWarning` for these tests — inspect-ai's async log
# reader / anyio memory stream occasionally leaves files / streams unclosed at
# GC time on the .eval log archive. The default project-level `filterwarnings`
# = "error" promotes ResourceWarning to a hard failure, masking the real
# assertion outcome. The leak is inside the inspect-ai library (not our code),
# so we silence it locally.
pytestmark = [
    pytest.mark.requires_api,
    pytest.mark.filterwarnings("default::ResourceWarning"),
    pytest.mark.filterwarnings("default::pytest.PytestUnraisableExceptionWarning"),
]

# Pinned model for all P0.2 smoke cases — Haiku for cost (Plan 38 §P0.2).
SMOKE_MODEL = "anthropic/claude-haiku-4-5"

# The trivial task reused across all three cases. We ask for `print("hello world")`
# (case-insensitive substring match) — robust to Haiku wrapping the snippet in
# backticks or surrounding prose.
SMOKE_INPUT = "Write a Python program that prints exactly: hello world"
SMOKE_TARGET = 'print("hello world")'


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.fixture(autouse=True)
def _skip_without_key() -> None:
    if not _has_api_key():
        pytest.skip("ANTHROPIC_API_KEY not set — skipping API-dependent test")


def _smoke_task(sandbox: str | None = None) -> Task:
    """Build the shared trivial Task — one sample, `includes()` scorer.

    `sandbox` is wired through for rungs that wrap agents requiring a sandbox
    (e.g. `inspect_swe.claude_code` injects bridged tools via sandbox). The
    bare-substrate Case A leaves it None.
    """
    return Task(
        dataset=[Sample(input=SMOKE_INPUT, target=SMOKE_TARGET)],
        scorer=includes(ignore_case=True),
        sandbox=sandbox,
    )


def _assert_score_one(log: EvalLog) -> None:
    """Assert the eval log has exactly one sample with score == 1.0."""
    assert log.status == "success", f"eval status was {log.status!r}, error={log.error!r}"
    assert log.samples is not None and len(log.samples) == 1, (
        f"expected 1 sample, got {None if log.samples is None else len(log.samples)}"
    )
    sample = log.samples[0]
    assert sample.scores is not None, "sample.scores is None"
    # `includes()` is registered as the sample's sole scorer — extract its value.
    score_values = [s.value for s in sample.scores.values()]
    assert score_values, "sample has no scorer values"
    # `includes()` returns "C" (correct) or "I" (incorrect); the metrics reducer
    # converts that to 1.0 / 0.0 on the EvalLog results, but per-sample value
    # is the raw letter. We accept either representation.
    primary = score_values[0]
    assert primary in ("C", 1.0, 1), f"expected score C / 1.0, got {primary!r}"


# Haiku 4.5 published pricing (USD per token), 2026-05.
# Source: https://www.anthropic.com/pricing — claude-haiku-4-5: $1/MTok input, $5/MTok output.
# Cache reads are billed at 0.1x input price; cache writes at 1.25x input price.
_HAIKU_4_5_INPUT_PER_TOK = 1.0 / 1_000_000
_HAIKU_4_5_OUTPUT_PER_TOK = 5.0 / 1_000_000
_HAIKU_4_5_CACHE_READ_PER_TOK = 0.1 / 1_000_000
_HAIKU_4_5_CACHE_WRITE_PER_TOK = 1.25 / 1_000_000


def _log_total_cost(log: EvalLog) -> float:
    """Estimate total cost (USD) for the eval log.

    Inspect AI's built-in `ModelUsage.total_cost` is `None` for models missing
    from its bundled pricing table (Haiku 4.5 isn't in v0.3.219). We compute
    from raw token counts using the published Haiku 4.5 pricing as a fallback
    so the per-test cost guardrail still bites.
    """
    if log.samples is None:
        return 0.0
    total = 0.0
    for sample in log.samples:
        usage_map = sample.model_usage or {}
        for usage in usage_map.values():
            published = getattr(usage, "total_cost", None)
            if published is not None:
                total += float(published)
                continue
            # Fallback: assume Haiku 4.5 pricing (all P0.2 cases use Haiku).
            in_tok = (usage.input_tokens or 0) - (usage.input_tokens_cache_read or 0)
            out_tok = usage.output_tokens or 0
            cache_read = usage.input_tokens_cache_read or 0
            cache_write = usage.input_tokens_cache_write or 0
            total += (
                in_tok * _HAIKU_4_5_INPUT_PER_TOK
                + out_tok * _HAIKU_4_5_OUTPUT_PER_TOK
                + cache_read * _HAIKU_4_5_CACHE_READ_PER_TOK
                + cache_write * _HAIKU_4_5_CACHE_WRITE_PER_TOK
            )
    return total


def test_case_a_bare_substrate(tmp_path: Path) -> None:
    """Case A — bare substrate.

    Plan 38 §P0.2 Case A: trivial Task, `generate()` solver, `includes()` scorer.
    Validates Inspect AI install end-to-end against Haiku. Asserts score=1.0.
    """
    logs = eval(
        _smoke_task(),
        model=SMOKE_MODEL,
        solver=generate(),
        log_dir=str(tmp_path / "logs"),
        display="none",
    )
    assert len(logs) == 1, f"expected one EvalLog, got {len(logs)}"
    _assert_score_one(logs[0])

    cost = _log_total_cost(logs[0])
    # Per-test guardrail per dispatch instructions.
    assert cost < 0.03, f"Case A cost {cost:.6f} exceeds $0.03 — investigate token usage"
    print(f"\n[Case A] cost: ${cost:.6f}")


def test_case_b_mini_swe_agent_smoke(tmp_path: Path) -> None:
    """Case B — `inspect_swe.mini_swe_agent()` smoke (rung 1 drop-in).

    Plan 38 §P0.2 Case B: trivial task with `rung1_raw_api()`. The pinned
    pre-registration config already nails the model to Haiku — the solver does
    not accept a `model=` override (see `bonsai_eval/solvers/rungs.py`).
    Asserts score=1.0.
    """
    solver = rung1_raw_api()
    logs = eval(
        _smoke_task(),
        model=SMOKE_MODEL,
        solver=solver,
        log_dir=str(tmp_path / "logs"),
        display="none",
    )
    assert len(logs) == 1
    _assert_score_one(logs[0])

    cost = _log_total_cost(logs[0])
    assert cost < 0.03, f"Case B cost {cost:.6f} exceeds $0.03 — investigate token usage"
    print(f"\n[Case B] cost: ${cost:.6f}")


def test_case_c_claude_code_workspace_suppression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Case C — `inspect_swe.claude_code()` smoke + workspace-suppression check.

    Plan 38 §P0.2 Case C: solver = `rung2_bare_cc(cwd=tmp_path)` invoked from a
    fresh tmp_path. Asserts:
      (1) score=1.0
      (2) no `CLAUDE.md` / `.claude/` materialized in cwd after the run
      (3) the Inspect EvalLog does NOT contain ambient station/CLAUDE.md content
          in any system message — grep for "Tech Lead Agent" and "Bonsai".

    If (3) fails, the bare-CC rung is leaking ambient workspace state. Per plan,
    DO NOT pivot to a `--no-inherit-claude-md` workaround here — stop and report.
    """
    # Fixture sanity: tmp_path must start empty.
    assert not any(tmp_path.iterdir()), "fixture sanity: tmp_path must start empty"

    # Also chdir, in case the underlying claude CLI defaults to cwd for workspace
    # discovery. Defense-in-depth — `rung2_bare_cc(cwd=...)` already pins cwd.
    monkeypatch.chdir(tmp_path)

    solver = rung2_bare_cc(cwd=tmp_path)
    logs = eval(
        # claude_code requires a sandbox to inject bridged tools — use `local`
        # (no Docker dependency for a smoke test). The solver pins `cwd=tmp_path`
        # for workspace isolation; the sandbox is an Inspect-side concern.
        _smoke_task(sandbox="local"),
        model=SMOKE_MODEL,
        solver=solver,
        log_dir=str(tmp_path / "logs"),
        display="none",
    )
    assert len(logs) == 1
    log = logs[0]

    # (1) score == 1.0
    _assert_score_one(log)

    # (2) no CLAUDE.md / .claude/ materialized in cwd
    leaked_paths: list[str] = []
    if (tmp_path / "CLAUDE.md").exists():
        leaked_paths.append(str(tmp_path / "CLAUDE.md"))
    if (tmp_path / ".claude").exists():
        leaked_paths.append(str(tmp_path / ".claude"))
    assert not leaked_paths, f"bare-CC rung materialized workspace files in cwd: {leaked_paths}"

    # (3) probe system messages for ambient station/ content.
    # `EvalLog.samples[i].messages` is the chat history; system messages have
    # role='system'. Search across all sample messages for the literal strings
    # "Tech Lead Agent" and "Bonsai" — both appear in station/CLAUDE.md and
    # would indicate the bare-CC rung inherited ambient workspace state.
    forbidden = ("Tech Lead Agent", "Bonsai")
    leaks: list[tuple[int, str, str]] = []
    assert log.samples is not None
    for sample in log.samples:
        for msg in sample.messages or []:
            if msg.role != "system":
                continue
            # `content` may be a str or a list of ContentText/ContentImage blocks.
            content = msg.content
            if isinstance(content, str):
                text = content
            else:
                parts: list[str] = []
                for block in content:
                    block_text = getattr(block, "text", None)
                    if isinstance(block_text, str):
                        parts.append(block_text)
                text = "\n".join(parts)
            for needle in forbidden:
                if needle in text:
                    leaks.append((sample.epoch, needle, text[:200]))
    assert not leaks, "ambient workspace state leaked into bare-CC system prompt:\n" + "\n".join(
        f"  epoch={e} needle={n!r} preview={p!r}" for e, n, p in leaks
    )

    cost = _log_total_cost(log)
    assert cost < 0.03, f"Case C cost {cost:.6f} exceeds $0.03 — investigate token usage"
    print(f"\n[Case C] cost: ${cost:.6f}")
