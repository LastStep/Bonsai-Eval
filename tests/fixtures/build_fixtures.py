"""Build synthetic placeholder fixtures for the analysis notebook.

Run from the repo root:

    uv run python tests/fixtures/build_fixtures.py

Produces `tests/fixtures/joined.parquet` — a 60-day synthetic timeseries
spanning the 2026-04-14 cutover so the notebook can run without touching
real transcripts (Plan 38 Risk #7).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).parent / "joined.parquet"
CUTOVER = date(2026, 4, 14)


def main() -> None:
    rng = np.random.default_rng(seed=42)
    rows = []
    for offset in range(-30, 31):
        d = CUTOVER + timedelta(days=offset)
        for slug in ["station", "control"]:
            base_cache = 0.4 if offset < 0 or slug == "control" else 0.65
            rows.append(
                {
                    "date": d.isoformat(),
                    "project_slug": slug,
                    "input_tokens": int(rng.integers(5_000, 20_000)),
                    "output_tokens": int(rng.integers(2_000, 8_000)),
                    "cache_read_tokens": int(
                        rng.integers(2_000, 25_000) * (1.5 if base_cache > 0.5 else 1.0)
                    ),
                    "cache_creation_tokens": int(rng.integers(100, 1000)),
                    "tool_calls": int(rng.integers(20, 200)),
                    "commits": int(rng.integers(0, 6)),
                    "feat_commits": int(rng.integers(0, 4)),
                    "fix_commits": int(rng.integers(0, 3)),
                    "rework_commits": int(rng.integers(0, 2)) if offset < 0 else 0,
                    "prs_merged": int(rng.integers(0, 3)),
                }
            )
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"wrote {OUT} ({len(df)} rows)")


if __name__ == "__main__":
    main()
