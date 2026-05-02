"""Shadow-thesis loader (issue #103).

Reads ``data/shadow_theses.jsonl`` produced by
``scripts/run_shadow_calibration.py`` and shapes each row into the
audit-log-compatible dict that ``backend.services.calibration``
expects, so the calibration endpoint can pool live + shadow rows.

The on-disk row shape:

    {
      "trigger_date": "2024-...",
      "z_at_trigger": 2.3,
      "spread_at_trigger": 7.1,
      "mode": "stub" | "foundry",
      "thesis": {
        "stance": "short_spread",
        "conviction_0_to_10": 7,
        "outcome": {"hit_target": true}
      },
      "scored_at": "..."
    }

After loading we wrap each row in a ``{"generated_at": ..., "thesis":
{...}}`` envelope to match the audit-log shape ``compute_calibration``
already understands.
"""

from __future__ import annotations

import json
import os
import pathlib


_DEFAULT_PATH = pathlib.Path(
    os.environ.get(
        "SHADOW_THESES_PATH",
        str(pathlib.Path(__file__).resolve().parents[2] / "data" / "shadow_theses.jsonl"),
    )
)


def load_shadow_rows(path: pathlib.Path | None = None) -> list[dict]:
    """Return the shadow theses as audit-log-compatible rows.

    Best-effort — missing file or malformed lines are skipped.
    """
    p = path or _DEFAULT_PATH
    if not p.exists():
        return []
    rows: list[dict] = []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                thesis = raw.get("thesis")
                if not isinstance(thesis, dict):
                    continue
                # Wrap in audit-log envelope so compute_calibration's
                # row.get("thesis") path works.
                rows.append(
                    {
                        "generated_at": raw.get("scored_at") or raw.get("trigger_date"),
                        "source": "shadow:" + str(raw.get("mode") or "stub"),
                        "thesis": thesis,
                    }
                )
    except Exception:
        return []
    return rows


__all__ = ["load_shadow_rows"]
