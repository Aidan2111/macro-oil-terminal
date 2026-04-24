"""Spread service — adapter over the legacy Brent/WTI pricing stack.

Calls ``providers.pricing.fetch_pricing_daily`` + ``quantitative_models
.compute_spread_zscore`` + ``language.describe_stretch`` to produce a
JSON-ready :class:`backend.models.spread.SpreadResponse`.

Kept deliberately thin: no caching here — caching lives at the router
layer (FastAPI dependency with a module-level TTL dict) so the service
stays trivially testable via ``monkeypatch``.
"""

from __future__ import annotations

from . import _compat  # noqa: F401  (must precede legacy imports)

import math

import pandas as pd

from ..models.spread import SpreadPoint, SpreadResponse


def _as_float(value: object) -> float | None:
    """Coerce a pandas/numpy scalar to ``float`` or ``None`` for NaN."""
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def get_spread_response(history_bars: int = 90) -> SpreadResponse:
    """Fetch daily Brent/WTI and return the shaped response model.

    Parameters
    ----------
    history_bars
        Number of trailing daily bars to include in ``history``. Defaults
        to 90, matching the rolling-Z window.
    """
    # Legacy module lookups go through _compat's sys.path injection.
    from providers import pricing  # type: ignore[import-not-found]
    from quantitative_models import compute_spread_zscore  # type: ignore[import-not-found]
    from language import describe_stretch  # type: ignore[import-not-found]

    result = pricing.fetch_pricing_daily()
    zframe: pd.DataFrame = compute_spread_zscore(result.frame)

    if zframe is None or zframe.empty:
        raise RuntimeError("compute_spread_zscore returned empty frame")

    tail = zframe.tail(history_bars)
    latest = zframe.iloc[-1]

    history = [
        SpreadPoint(
            date=pd.Timestamp(idx).date().isoformat(),
            brent=_as_float(row.get("Brent")),
            wti=_as_float(row.get("WTI")),
            spread=_as_float(row.get("Spread")),
            z_score=_as_float(row.get("Z_Score")),
        )
        for idx, row in tail.iterrows()
    ]

    brent_latest = _as_float(latest.get("Brent"))
    wti_latest = _as_float(latest.get("WTI"))
    spread_latest = _as_float(latest.get("Spread"))
    stretch = _as_float(latest.get("Z_Score"))

    if brent_latest is None or wti_latest is None or spread_latest is None:
        raise RuntimeError("latest bar has NaN Brent/WTI/Spread")

    band = describe_stretch(stretch if stretch is not None else 0.0)
    as_of = pd.Timestamp(zframe.index[-1]).date().isoformat()

    return SpreadResponse(
        brent=brent_latest,
        wti=wti_latest,
        spread=spread_latest,
        stretch=stretch,
        stretch_band=band,
        as_of=as_of,
        source=result.source,
        history=history,
    )
