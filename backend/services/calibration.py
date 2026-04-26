"""Confidence calibration for the /track-record page.

We bucket past theses by stated confidence (``conviction_0_to_10``)
into four bands — 0-2.5 / 2.5-5.0 / 5.0-7.5 / 7.5-10.0 (mapped to
0-25% / 25-50% / 50-75% / 75-100%) — and compute the realised hit
rate inside each bucket. A perfectly-calibrated model puts up
hit-rates that line up on the diagonal (predicted=actual). Drift
from the diagonal tells us we're either overconfident
(hit-rate < stated confidence in the high buckets) or
underconfident.

The verdict is backed by the **Brier score**:

  Brier = (1/N) * sum( (predicted_prob - actual_outcome)^2 )

We additionally compute the **mean signed error** (predicted minus
actual hit-rate, weighted by bucket size). Positive mean signed
error means overconfident; negative means underconfident; near zero
+ low Brier means well-calibrated.

Verdict thresholds (calibrated against a synthetic perfectly-
calibrated reference fixture; see tests):

  * ``brier <= 0.10`` AND ``abs(mean_signed_error) <= 0.05`` -> "calibrated"
  * ``mean_signed_error > 0.05``                              -> "overconfident"
  * ``mean_signed_error < -0.05``                             -> "underconfident"
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable, Sequence

from . import _compat  # noqa: F401


# Confidence buckets — half-open [lo, hi) on the 0-1 probability scale.
# The upper bucket is closed at 1.0 so 100% confidence lands in it.
BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.00, 0.25, "0-25%"),
    (0.25, 0.50, "25-50%"),
    (0.50, 0.75, "50-75%"),
    (0.75, 1.001, "75-100%"),
)


@dataclass(frozen=True)
class BucketStat:
    label: str
    lo: float
    hi: float
    midpoint: float
    n: int
    hits: int
    hit_rate: float


@dataclass(frozen=True)
class CalibrationStats:
    n_total: int
    brier_score: float
    mean_signed_error: float
    verdict: str
    buckets: tuple[BucketStat, ...]

    def to_dict(self) -> dict:
        d = asdict(self)
        # asdict already turns dataclass -> dict for nested BucketStat
        d["buckets"] = [asdict(b) for b in self.buckets]
        return d


def _conviction_to_prob(conv: float | None) -> float | None:
    """Map ``conviction_0_to_10`` (the legacy field name) onto a
    probability in [0, 1]. Returns ``None`` if the input is unusable."""
    if conv is None:
        return None
    try:
        v = float(conv)
    except (TypeError, ValueError):
        return None
    if v < 0 or v > 10:
        return None
    return v / 10.0


def _extract_outcome(thesis: dict) -> tuple[float | None, bool | None]:
    """Pull (predicted_prob, hit) out of an audit row's ``thesis`` dict.

    The audit shape is ``{"thesis": {"conviction_0_to_10": ..., "outcome":
    {"hit_target": bool}}}`` — defensively handle missing keys."""
    conv = thesis.get("conviction_0_to_10") if thesis else None
    prob = _conviction_to_prob(conv)
    outcome = (thesis or {}).get("outcome") or {}
    hit = outcome.get("hit_target")
    if hit is None:
        return prob, None
    return prob, bool(hit)


def compute_calibration(theses: Iterable[dict]) -> CalibrationStats:
    """Compute calibration stats across a list of past thesis rows.

    Parameters
    ----------
    theses
        Iterable of audit rows in the same shape as
        ``/api/thesis/history``. Rows without a confidence or
        without a closed outcome are silently dropped — same
        contract as the existing ``filterHighConfidenceActioned``
        on the frontend.
    """
    pairs: list[tuple[float, bool]] = []
    for row in theses:
        thesis = row.get("thesis") if isinstance(row, dict) else None
        if not thesis:
            continue
        prob, hit = _extract_outcome(thesis)
        if prob is None or hit is None:
            continue
        pairs.append((prob, hit))

    n = len(pairs)
    if n == 0:
        return CalibrationStats(
            n_total=0,
            brier_score=0.0,
            mean_signed_error=0.0,
            verdict="insufficient_data",
            buckets=tuple(
                BucketStat(label, lo, hi, (lo + min(hi, 1.0)) / 2, 0, 0, 0.0)
                for lo, hi, label in BUCKETS
            ),
        )

    # Per-bucket hit rates
    bucket_stats: list[BucketStat] = []
    weighted_signed_err = 0.0
    for lo, hi, label in BUCKETS:
        in_bucket = [(p, h) for p, h in pairs if lo <= p < hi]
        n_b = len(in_bucket)
        hits_b = sum(1 for _, h in in_bucket if h)
        hit_rate = hits_b / n_b if n_b else 0.0
        # Cap midpoint at 1.0 visually for the top bucket (the 1.001
        # in BUCKETS is just to make the half-open range catch 100%).
        mid = (lo + min(hi, 1.0)) / 2.0
        bucket_stats.append(
            BucketStat(label, lo, hi, mid, n_b, hits_b, hit_rate)
        )
        if n_b:
            # Signed error = predicted (mid) - actual (hit_rate). We
            # weight by bucket population so a tiny bucket with extreme
            # error doesn't dominate the verdict.
            weighted_signed_err += (mid - hit_rate) * n_b

    mean_signed_err = weighted_signed_err / n

    # Brier — uses the actual stated probability, not the bucket mid.
    brier = sum((p - (1.0 if h else 0.0)) ** 2 for p, h in pairs) / n

    if brier <= 0.10 and abs(mean_signed_err) <= 0.05:
        verdict = "calibrated"
    elif mean_signed_err > 0.05:
        verdict = "overconfident"
    elif mean_signed_err < -0.05:
        verdict = "underconfident"
    else:
        # High brier but small signed error — noisy, not biased.
        verdict = "noisy"

    return CalibrationStats(
        n_total=n,
        brier_score=brier,
        mean_signed_error=mean_signed_err,
        verdict=verdict,
        buckets=tuple(bucket_stats),
    )


__all__ = ["BucketStat", "CalibrationStats", "compute_calibration", "BUCKETS"]
