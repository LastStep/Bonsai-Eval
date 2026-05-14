"""Scorers — Plan 38 §P2.3 + SCHEMA.md §Evaluators.

Exposes:

  - `evaluate_deterministic` — six deterministic check helpers.
  - `evaluate_test_based`    — sandbox / subprocess command runner.
  - `evaluate_llm_judge`     — Haiku judge with position-swap.
  - `build_scorer`           — Inspect `Scorer` factory that composes a
                                scenario's `evaluators` list into a
                                single Scorer. Pass-rule: scenario
                                passes iff ALL evaluators pass; per-
                                evaluator details land on Score.metadata
                                for downstream analysis.

The factory is intentionally pluggable: the `client_factory` argument is
the seam unit tests use to inject a mock Anthropic client, and the
`baseline_hashes` / `workspace_root` arguments are injected by the
rung-3 setup solver (P2.4) at task-construction time.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from inspect_ai.scorer import Score, Scorer, Target, accuracy, mean, scorer
from inspect_ai.solver import TaskState

from bonsai_eval.scorers.deterministic import (
    CheckResult,
    evaluate_deterministic,
    file_contains,
    file_exists,
    file_unchanged,
    hook_event_fired,
    tool_call_made,
    tool_call_not_made,
)
from bonsai_eval.scorers.llm_judge import (
    JudgeClient,
    JudgeVerdict,
    evaluate_llm_judge,
    render_prompt,
    run_position_swap_judge,
)
from bonsai_eval.scorers.test_based import evaluate_test_based


def _default_client_factory() -> JudgeClient:
    """Lazy import + construct the real Anthropic client.

    Late import so unit tests that never instantiate this factory don't pay
    the `anthropic` import cost, and so missing `ANTHROPIC_API_KEY` only
    bites the live-judge path.
    """
    import anthropic  # noqa: PLC0415

    # Anthropic SDK's `messages.create()` return type is structurally
    # compatible with our narrow `JudgeClient` Protocol (we read only
    # `.content[i].text`). Mypy can't see through the Protocol-vs-concrete
    # name mismatch, so the cast is the documented escape hatch.
    return anthropic.Anthropic()  # type: ignore[return-value]


@scorer(metrics=[accuracy(), mean()])
def build_scorer(
    evaluators: list[dict[str, Any]],
    *,
    workspace_root: Path | None = None,
    baseline_hashes: dict[str, str] | None = None,
    client_factory: Callable[[], JudgeClient] | None = None,
) -> Scorer:
    """Compose a scenario's evaluator list into a single Inspect `Scorer`.

    Args:
        evaluators: The scenario's `evaluators` list (post-validation).
        workspace_root: Filesystem root for relative-path resolution in
            `file_*` checks. Defaults to `cwd`. The rung-3 setup solver
            (P2.4) overrides this to the materialized workspace path; the
            rung-1 / rung-2 paths leave it at cwd (which is the sandbox's
            own cwd when running under Docker).
        baseline_hashes: Map of `path -> SHA-256 hex` captured BEFORE the
            agent acted. Used by `file_unchanged` checks. The setup solver
            populates this; an empty dict means "no baselines captured",
            in which case `file_unchanged` falls back to its absence
            semantics (see `deterministic.file_unchanged`).
        client_factory: Zero-arg callable returning a `JudgeClient`. Tests
            override this to inject a mock; production code leaves it
            `None` and gets the real `anthropic.Anthropic`.

    Pass rule: scenario passes iff EVERY evaluator passes. Per-evaluator
    details land on `Score.metadata['evaluators']` as a list of
    `{type, check, passed, detail}` dicts so downstream analysis can
    diff individual checks even when the headline score is 0/1.

    The returned scorer is a coroutine compatible with Inspect's `Scorer`
    protocol (`async def (state, target) -> Score`).
    """
    # NB: `workspace_root` / `baseline_hashes` are resolved per-call below.
    # If the caller didn't pass them, we honour metadata stashed by the
    # rung-3 setup solver (`bonsai_eval.solvers.rungs.rung3_setup_solver`)
    # which writes `state.metadata['workspace_root' / 'baseline_hashes']`.
    explicit_workspace_root = workspace_root
    explicit_baseline_hashes = baseline_hashes
    client_factory = client_factory or _default_client_factory

    async def score(state: TaskState, target: Target) -> Score:
        del target  # SCHEMA.md scenarios don't use the Inspect `target` field.
        meta = getattr(state, "metadata", None) or {}
        effective_workspace_root: Path
        if explicit_workspace_root is not None:
            effective_workspace_root = explicit_workspace_root
        elif "workspace_root" in meta:
            effective_workspace_root = Path(meta["workspace_root"])
        else:
            effective_workspace_root = Path.cwd()
        if explicit_baseline_hashes is not None:
            effective_baseline_hashes = explicit_baseline_hashes
        else:
            effective_baseline_hashes = dict(meta.get("baseline_hashes") or {})
        details: list[dict[str, Any]] = []
        all_passed = True

        # Pull the agent's final response for the judge. Inspect populates
        # `state.output.completion` with the assistant's final message;
        # fall back to the last assistant message text if absent.
        agent_response = _last_assistant_text(state)
        prompt = state.input_text if hasattr(state, "input_text") else ""

        for ev in evaluators:
            etype = ev.get("type")
            try:
                if etype == "deterministic":
                    passed, detail = evaluate_deterministic(
                        ev,
                        transcript=state,
                        workspace_root=effective_workspace_root,
                        baseline_hashes=effective_baseline_hashes,
                    )
                elif etype == "test_based":
                    passed, detail = await evaluate_test_based(
                        ev,
                        workspace_root=effective_workspace_root,
                    )
                elif etype == "llm_judge":
                    passed, detail = evaluate_llm_judge(
                        ev,
                        agent_response=agent_response,
                        prompt=prompt,
                        client=client_factory(),
                    )
                else:
                    passed, detail = (False, f"unknown evaluator type: {etype!r}")
            except Exception as exc:  # pragma: no cover — defensive
                passed = False
                detail = f"{etype}: raised {type(exc).__name__}: {exc}"
            details.append(
                {
                    "type": etype,
                    "check": ev.get("check"),
                    "tool": ev.get("tool"),
                    "passed": passed,
                    "detail": detail,
                }
            )
            if not passed:
                all_passed = False

        return Score(
            value=1.0 if all_passed else 0.0,
            answer=agent_response[:500],
            explanation=_explain(details),
            metadata={"evaluators": details},
        )

    return score


def _last_assistant_text(state: TaskState) -> str:
    """Best-effort extraction of the agent's final assistant message text."""
    output = getattr(state, "output", None)
    if output is not None:
        completion = getattr(output, "completion", None)
        if isinstance(completion, str) and completion:
            return completion
    # Fall back to walking messages backward.
    for msg in reversed(getattr(state, "messages", []) or []):
        if getattr(msg, "role", None) == "assistant":
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [getattr(b, "text", "") for b in content if getattr(b, "text", None)]
                return "\n".join(parts)
    return ""


def _explain(details: list[dict[str, Any]]) -> str:
    """Render the per-evaluator details into a human-readable Score.explanation."""
    lines: list[str] = []
    for d in details:
        mark = "PASS" if d["passed"] else "FAIL"
        check_label = d.get("check") or d.get("type") or "?"
        lines.append(f"  [{mark}] {d['type']}/{check_label}: {d['detail']}")
    return "\n".join(lines) if lines else "(no evaluators)"


__all__ = [
    "CheckResult",
    "JudgeClient",
    "JudgeVerdict",
    "build_scorer",
    "evaluate_deterministic",
    "evaluate_llm_judge",
    "evaluate_test_based",
    "file_contains",
    "file_exists",
    "file_unchanged",
    "hook_event_fired",
    "render_prompt",
    "run_position_swap_judge",
    "tool_call_made",
    "tool_call_not_made",
]
