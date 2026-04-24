"""CFTC service — adapter over ``providers._cftc``.

Calls ``fetch_wti_positioning`` + ``managed_money_zscore`` and shapes
the weekly COT frame into a :class:`CFTCResponse`.
"""

from __future__ import annotations

from . import _compat  # noqa: F401

import pandas as pd

from ..models.cftc import CFTCPoint, CFTCResponse


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def get_cftc_response() -> CFTCResponse:
    """Fetch ~3y of WTI positioning + latest snapshot."""
    from providers import _cftc  # type: ignore[import-not-found]

    result = _cftc.fetch_wti_positioning()
    frame: pd.DataFrame = result.frame
    if frame is None or frame.empty:
        raise RuntimeError("CFTC provider returned empty frame")

    history = [
        CFTCPoint(
            date=pd.Timestamp(idx).date().isoformat(),
            mm_net=_as_int(row.get("mm_net")),
            producer_net=_as_int(row.get("producer_net")),
            swap_net=_as_int(row.get("swap_net")),
            open_interest=_as_int(row.get("open_interest")),
        )
        for idx, row in frame.iterrows()
    ]

    latest = frame.iloc[-1]
    mm_net = _as_int(latest.get("mm_net")) or 0
    producer_net = _as_int(latest.get("producer_net")) or 0
    swap_net = _as_int(latest.get("swap_net")) or 0
    commercial_net = producer_net + swap_net

    z = _cftc.managed_money_zscore(frame)
    mm_z = float(z) if z is not None else None

    as_of = pd.Timestamp(frame.index[-1]).date().isoformat()

    return CFTCResponse(
        mm_net=mm_net,
        commercial_net=commercial_net,
        mm_zscore_3y=mm_z,
        as_of=as_of,
        market=str(latest.get("market") or result.market_name or ""),
        source_url=result.source_url,
        history=history,
    )
