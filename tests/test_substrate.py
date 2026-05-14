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

# The trivial task reused across all three cases. The target is `hello world`
# (case-insensitive substring) — robust across:
#   - Case A (`generate()`): the model's response includes `print("hello world")`
#     which contains the literal `hello world`.
#   - Case B (`mini_swe_agent`): the agent's final summary message acknowledges
#     the task and quotes back "hello world".
#   - Case C (`claude_code`): same as Case B.
# The `includes()` scorer evaluates `state.output.completion` which is the
# agent's last assistant message — agentic solvers do not echo the literal
# `print("hello world")` snippet in their summary text, so we score on the
# semantic answer ("hello world") rather than the syntactic form.
SMOKE_INPUT = (
    "Write a Python program that prints exactly: hello world\n"
    "In your final message, confirm what your program prints."
)
SMOKE_TARGET = "hello world"


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
            # Inspect AI's `ModelUsage.input_tokens` is the *non-cached* input
            # count — cache reads/writes are tracked in separate fields. Do NOT
            # subtract them out again (Anthropic returns them as disjoint
            # counters: empirically `input_tokens=34, cache_read=60587` for a
            # run with extensive prompt caching).
            in_tok = usage.input_tokens or 0
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
        # `inspect_swe.mini_swe_agent` requires a sandbox for the resumable agent
        # plumbing + bridge proxy. Docker is the only supported kind for the
        # bridged-tools path; daemon up confirmed in Plan 38 §Manual Prep step 6.
        _smoke_task(sandbox="docker"),
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


def test_case_c_claude_code_workspace_suppression(tmp_path: Path) -> None:
    """Case C — `inspect_swe.claude_code()` smoke + workspace-suppression check.

    Plan 38 §P0.2 Case C + §Risks #1 (re-opened 2026-05-14): solver =
    `rung2_bare_cc(cwd=tmp_path, home_dir=tmp_home)` invoked from a fresh
    tmp_path with an empty `tmp_home` redirected as the sandbox `HOME`.
    Asserts:
      (1) score=1.0
      (2) no `CLAUDE.md` / `.claude/` materialized in cwd after the run
      (3) the Inspect EvalLog does NOT contain ambient station/CLAUDE.md
          content in any system message — grep for "Tech Lead Agent" and
          "Bonsai". With `HOME` redirected to an empty tmp dir, the bare-CC
          rung must inherit no ambient `~/.claude/` state.

    If (3) fails EVEN WITH `HOME` redirected, the bare-CC rung is leaking
    ambient workspace state — per plan §P0.2 we STOP and ESCALATE rather
    than improvising a workaround.
    """
    # Fixture sanity: tmp_path must start empty.
    assert not any(tmp_path.iterdir()), "fixture sanity: tmp_path must start empty"

    # Empty home dir for the sandbox per Plan 38 §Risks #1 (re-opened
    # 2026-05-14). We create the directory on the host (purely to give the
    # test a unique, valid filesystem path string), then pass the path to the
    # solver as `home_dir=`. Inside the Docker sandbox, the host directory
    # isn't bind-mounted — but the agent's `_seed_claude_config()` runs
    # `mkdir -p "$HOME/.claude"` in the container, so any valid path string
    # works. The empty-dir guarantee is what blocks `~/.claude/` inheritance.
    tmp_home = tmp_path / "home"
    tmp_home.mkdir()

    solver = rung2_bare_cc(home_dir=tmp_home)
    logs = eval(
        # `inspect_swe.claude_code` requires a Docker sandbox — `LocalSandboxEnvironment`
        # rejects the `user=` plumbing the agent uses. Docker daemon up confirmed
        # in Plan 38 §Manual Prep step 6.
        _smoke_task(sandbox="docker"),
        model=SMOKE_MODEL,
        solver=solver,
        log_dir=str(tmp_path / "logs"),
        display="none",
    )
    assert len(logs) == 1
    log = logs[0]

    # (1) score == 1.0
    _assert_score_one(log)

    # (2) no `CLAUDE.md` / `.claude/` materialized in the test's fresh
    # `tmp_path`. The Docker sandbox is filesystem-isolated from the host by
    # default (no bind mounts in inspect-ai's generic compose), so this is
    # structurally guaranteed — we assert explicitly to catch future
    # regressions if a mount is ever added to the default config. We exclude
    # the `logs/` subdir (the eval log dir is `tmp_path / "logs"`).
    leaked_paths: list[str] = []
    for child in tmp_path.iterdir():
        if child.name == "logs":
            continue
        if child.name in {"CLAUDE.md", ".claude"}:
            leaked_paths.append(str(child))
    assert not leaked_paths, (
        f"bare-CC rung materialized workspace files in tmp_path: {leaked_paths}"
    )

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
