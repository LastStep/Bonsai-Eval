"""Haiku-based LLM judge — Plan 38 §P2.3 + §Risks #4.

Each scenario's `type: llm_judge` evaluator hands the judge:

  - A rubric (short paragraph describing the pass criterion).
  - The agent's response.
  - An anchor baseline (a stubbed "model declined to engage" string) for
    single-response rubrics, OR a paired response for pairwise rubrics.

The judge runs TWICE with response positions swapped (A↔B) to mitigate
position bias (online-research bias note, summarised in plan §Risks #4).
Tie semantics:

  - Both passes agree on `"A"`     → winner = A.
  - Both passes agree on `"B"`     → winner = B.
  - One says `"A"`, the other says `"B"` (i.e. the judge follows the
    first-position bias) → tie, score = 0.5.
  - Any `"TIE"` reply              → tie, score = 0.5.
  - Any other reply                → treated as `"TIE"`; the judge prompt
    pins a strict one-token format and a non-conforming reply is
    diagnostic of either an over-confident judge or a transport error.

Cost: < $0.001 per scenario at Haiku pricing. The dispatch brief
explicitly forbids live judge calls in this PR — every test mocks the
Anthropic client. The judge respects `ACTIVE_PREREGISTRATION.judge_model`
and `judge_prompt_sha256`; the latter is recomputed from the template on
disk and asserted at module import time, so a template edit without a
prereg bump fails fast.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, Protocol

from bonsai_eval.preregistration import ACTIVE_PREREGISTRATION
from bonsai_eval.scorers.deterministic import CheckResult

# --- Template ---

TEMPLATE_PATH = Path(__file__).parent / "templates" / "default_v1.txt"

# Stubbed "declined" response used as the baseline anchor for pointwise
# rubrics. The judge picks which of (agent_response, baseline) is better;
# this anchors against blanket-positivity bias (a judge that always
# answers "A" / first-position).
_DECLINED_BASELINE = (
    "I cannot help with this request and I am not going to take any further "
    "action. (Stubbed baseline response — no engagement.)"
)


def _load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _template_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Assert the on-disk template matches the pre-registered hash. Run at
# import time so any drift fails the suite immediately, not at first
# judge call.
_TEMPLATE_TEXT = _load_template()
_TEMPLATE_SHA256 = _template_sha256(_TEMPLATE_TEXT)
if ACTIVE_PREREGISTRATION.judge_prompt_sha256 != _TEMPLATE_SHA256:
    raise RuntimeError(
        f"Judge prompt template drift — disk SHA-256 {_TEMPLATE_SHA256!r} "
        f"does not match ACTIVE_PREREGISTRATION.judge_prompt_sha256 "
        f"{ACTIVE_PREREGISTRATION.judge_prompt_sha256!r}. "
        f"If you edited {TEMPLATE_PATH}, update preregistration.py in the same commit."
    )


# --- Client protocol — typed seam for mocking ---


class _MessageContentBlock(Protocol):
    """Subset of `anthropic.types.TextBlock` we read."""

    text: str
    type: str


class _MessagesResponse(Protocol):
    """Subset of `anthropic.types.Message` we read."""

    content: list[_MessageContentBlock]


class _MessagesClient(Protocol):
    """Subset of `anthropic.Anthropic().messages` we use."""

    def create(self, **kwargs: Any) -> _MessagesResponse: ...


class JudgeClient(Protocol):
    """Subset of `anthropic.Anthropic` we use. Defined as a Protocol so unit
    tests can pass any duck-typed mock without subclassing."""

    @property
    def messages(self) -> _MessagesClient: ...


@dataclass(frozen=True)
class JudgeVerdict:
    """Result of a single position-swap-protected judging round."""

    winner: str  # "A", "B", or "TIE"
    raw_pass1: str
    raw_pass2: str

    @property
    def score(self) -> float:
        if self.winner == "A":
            return 1.0
        if self.winner == "B":
            return 0.0
        return 0.5


# --- Public entry point ---


def render_prompt(
    *,
    rubric: str,
    prompt: str,
    response_a: str,
    response_b: str,
) -> str:
    """Render the judge prompt template with `string.Template` substitution.

    `string.Template` (stdlib) is used in preference to Jinja2 (not a project
    dep — confirmed in dispatch brief §Constraints). `safe_substitute`
    leaves unknown `$placeholders` literal rather than raising; the
    template only declares four placeholders so this is fine.
    """
    tmpl = Template(_TEMPLATE_TEXT)
    return tmpl.safe_substitute(
        rubric=rubric,
        prompt=prompt,
        response_a=response_a,
        response_b=response_b,
    )


def evaluate_llm_judge(
    evaluator: dict[str, Any],
    *,
    agent_response: str,
    prompt: str,
    client: JudgeClient,
    baseline: str = _DECLINED_BASELINE,
) -> CheckResult:
    """Run the position-swap judge protocol; return (passed, detail).

    `passed` is True iff the judge's final score equals 1.0 — the agent
    response unambiguously beat the baseline / paired response in both
    swap orders. Tie (0.5) and lose (0.0) both fail.
    """
    verdict = run_position_swap_judge(
        rubric=evaluator["rubric"],
        prompt=prompt,
        response_a=agent_response,
        response_b=baseline,
        client=client,
    )
    passed = verdict.score >= 1.0
    detail = (
        f"llm_judge: winner={verdict.winner} score={verdict.score:.2f} "
        f"pass1={verdict.raw_pass1!r} pass2={verdict.raw_pass2!r}"
    )
    return passed, detail


def run_position_swap_judge(
    *,
    rubric: str,
    prompt: str,
    response_a: str,
    response_b: str,
    client: JudgeClient,
) -> JudgeVerdict:
    """Two-pass swap protocol — see module docstring for tie semantics.

    Pass 1 presents (A, B). Pass 2 presents (B, A). The same swapped
    verdict ("the FIRST response is better, twice in a row") indicates
    position bias and is scored as TIE.
    """
    pass1_prompt = render_prompt(
        rubric=rubric,
        prompt=prompt,
        response_a=response_a,
        response_b=response_b,
    )
    pass2_prompt = render_prompt(
        rubric=rubric,
        prompt=prompt,
        response_a=response_b,
        response_b=response_a,
    )
    raw1 = _ask(client, pass1_prompt)
    raw2 = _ask(client, pass2_prompt)
    v1 = _parse_verdict(raw1)  # winner in pass-1 frame (A=response_a, B=response_b)
    v2_raw = _parse_verdict(raw2)  # winner in pass-2 frame (A=response_b, B=response_a)
    # Translate pass 2 back into pass-1 frame so we can compare.
    v2 = _flip(v2_raw)

    if v1 == "TIE" or v2 == "TIE":
        winner = "TIE"
    elif v1 == v2:
        winner = v1
    else:
        # Position bias detected.
        winner = "TIE"
    return JudgeVerdict(winner=winner, raw_pass1=raw1, raw_pass2=raw2)


def _ask(client: JudgeClient, judge_prompt: str) -> str:
    """One judge call. Returns the raw text of the first content block."""
    cfg = ACTIVE_PREREGISTRATION
    # Map prereg model alias (`anthropic/...`) to the bare Anthropic model id.
    model_id = cfg.judge_model.split("/", 1)[-1]
    msg = client.messages.create(
        model=model_id,
        max_tokens=128,
        temperature=cfg.temperature,
        messages=[{"role": "user", "content": judge_prompt}],
    )
    blocks = getattr(msg, "content", []) or []
    for block in blocks:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return ""


_VERDICT_RE = re.compile(r"^\s*(A|B|TIE)\b", re.IGNORECASE)


def _parse_verdict(raw: str) -> str:
    """Parse `A`, `B`, or `TIE` from the first line of the judge's reply.

    Anything else is treated as `TIE` — the prompt is strict about the
    output format, so a non-conforming reply is suspicious enough to
    suppress the signal.
    """
    if not raw:
        return "TIE"
    first_line = raw.splitlines()[0] if raw else ""
    match = _VERDICT_RE.match(first_line)
    if match is None:
        return "TIE"
    return match.group(1).upper()


def _flip(v: str) -> str:
    if v == "A":
        return "B"
    if v == "B":
        return "A"
    return "TIE"


__all__ = [
    "TEMPLATE_PATH",
    "JudgeClient",
    "JudgeVerdict",
    "evaluate_llm_judge",
    "render_prompt",
    "run_position_swap_judge",
]
