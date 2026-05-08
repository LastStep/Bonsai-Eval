"""Codeburn fetcher — Plan 38 §P1.1.

Wraps `codeburn export` and dumps JSON to `data/raw/codeburn-<date>.json`.
Idempotent within the same day (overwrites). Schema is pinned to
`codeburn.export.v2` per Plan 38 §Risks #2; mismatch raises a clear error.

If the `codeburn` CLI isn't installed (e.g. in CI), `fetch_codeburn` is a
no-op that returns None — `make telemetry` still succeeds.

**Flag-set discrepancy (resolved 2026-05-08).** Plan 38 §P1.1 listed flags
`--per-project-daily`, `--since`, `--include-turns`, `--include-activity-by-project`
that don't exist in `codeburn 0.8.7`. The plan's verification step ("confirm
exact flag names against `codeburn --help` first") landed here — actual flags
are `--format json -o <path>`. The export already includes today + 7d + 30d
windows by default and the JSON shape contains per-project, per-session, and
per-tool breakdowns under top-level keys `projects`, `sessions`, `tools`,
`periods`, `summary`. Schema check pins us to `codeburn.export.v2` so a future
breaking change still fails fast.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

EXPECTED_SCHEMA = "codeburn.export.v2"


def codeburn_available() -> bool:
    """Return True iff the `codeburn` CLI is on PATH."""
    return shutil.which("codeburn") is not None


def output_path_for(*, output_dir: Path, today: date | None = None) -> Path:
    """Compute the deterministic output filename for today's export."""
    today = today or date.today()
    return output_dir / f"codeburn-{today.isoformat()}.json"


def fetch(
    *,
    output_dir: Path,
    today: date | None = None,
) -> Path | None:
    """Run `codeburn export` and write JSON. Returns path on success, None when CLI absent.

    If a future codeburn release breaks the schema, this raises a clear error
    so the pipeline fails fast (Plan 38 §Risks #2).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_path_for(output_dir=output_dir, today=today)

    if not codeburn_available():
        # Fall through silently — `make telemetry` is expected to run on
        # machines where codeburn isn't installed (CI, fresh clones).
        return None

    cmd = ["codeburn", "export", "--format", "json", "-o", str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    # Validate schema by reading back what codeburn just wrote.
    payload = json.loads(out_path.read_text())
    schema = payload.get("schema") or payload.get("schema_version")
    if schema != EXPECTED_SCHEMA:
        raise RuntimeError(
            f"codeburn schema mismatch: got {schema!r}, expected {EXPECTED_SCHEMA!r}. "
            "If codeburn shipped a new major version, update EXPECTED_SCHEMA "
            "in bonsai_eval.telemetry.fetch_codeburn after auditing the new shape."
        )

    return out_path
