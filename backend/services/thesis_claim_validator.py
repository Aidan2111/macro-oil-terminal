"""Thesis numeric-claim validator (issue #98).

The Foundry agent emits a structured thesis (stance, conviction,
plain-English headline, key drivers, invalidation risks, reasoning
summary). Nothing in the pipeline checks that **numeric claims in
the natural-language fields actually trace back to the structured
context payload**. If the LLM writes "Brent is $999/bbl" but the
real `latest_brent` is $108, the user can't tell — the headline
reads convincingly either way.

This module scans the LLM's free-text fields for numeric claims
(`\\d+(?:\\.\\d+)?` plus a unit token like USD/%/sigma/bbl/days)
and asserts every claim falls within a configurable tolerance
(default ±5%) of *some* numeric field in the structured context.

We deliberately use a permissive matching strategy:

  * Walk the context dict recursively, collect every numeric leaf
    into a flat list.
  * For each numeric claim in the text, accept if ANY context value
    is within tolerance (relative or absolute, depending on
    magnitude). This catches the "$999/bbl" hallucination because
    no context value is in that ballpark, while letting through
    legitimate prose like "Brent is around $108" (matches
    `latest_brent`).
  * Hard pin checks for unambiguous units: a number followed by
    "sigma" / "σ" must trace specifically to a sigma-bearing
    context field (current_z, garch_z) — not just any random
    number.

The validator is non-destructive: it returns a verdict + list of
violations. The thesis pipeline can decide whether to retry with a
"do not invent numbers" nudge, strip the offending sentence, or
just surface the verdict to the UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# Units we recognise — paired with the context fields they typically
# trace to. The matcher uses the unit to decide whether a strict
# specialised pin-check applies; absent a unit, we fall back to the
# loose "any numeric context value" check.
_SIGMA_UNIT_TOKENS = {"sigma", "σ", "stdev", "stdevs", "stddev"}
_DOLLAR_UNIT_TOKENS = {"usd", "$", "/bbl"}
_PERCENT_UNIT_TOKENS = {"%", "pct", "percent"}
_DAYS_UNIT_TOKENS = {"day", "days"}


# Regex that matches a signed number with optional decimal + an optional
# trailing unit token. The unit-token matching is permissive — "USD",
# "$110", "$11.20", "11/bbl" are all caught. We capture both the value
# and a small window of preceding/following text for context.
_NUMBER_PATTERN = re.compile(
    r"(?P<prefix>\$)?"
    r"(?P<value>[+-]?\d+(?:\.\d+)?)"
    r"\s*"
    r"(?P<unit>%|σ|usd/bbl|usd|\$|kbbl|mbbl|kbpd|mbpd|mmbbl|bbl|sigma|stdev|stdevs|stddev|days|day|pct|percent)?",
    re.IGNORECASE,
)


@dataclass
class ClaimViolation:
    """A numeric claim that doesn't trace to the structured context."""

    field: str            # which thesis field contained the claim
    value: float          # the numeric value the LLM wrote
    unit: str | None      # "$", "%", "sigma", "days", etc. (lowercased)
    snippet: str          # ~40 chars of surrounding text
    reason: str           # human-readable explanation


def _flatten_context_numerics(ctx: Any, prefix: str = "") -> list[tuple[str, float]]:
    """Walk a context dict / dataclass-asdict and return every
    (path, numeric_value) pair. Strings, None, and bools are skipped.
    """
    out: list[tuple[str, float]] = []
    if ctx is None:
        return out
    if isinstance(ctx, bool):
        return out  # bools are an int subclass — skip
    if isinstance(ctx, (int, float)):
        try:
            f = float(ctx)
        except Exception:
            return out
        # NaN / inf are useless for matching.
        if f != f or f in (float("inf"), float("-inf")):
            return out
        out.append((prefix or "<root>", f))
        return out
    if isinstance(ctx, dict):
        for k, v in ctx.items():
            sub = f"{prefix}.{k}" if prefix else str(k)
            out.extend(_flatten_context_numerics(v, sub))
        return out
    if isinstance(ctx, (list, tuple)):
        for i, v in enumerate(ctx):
            out.extend(_flatten_context_numerics(v, f"{prefix}[{i}]"))
        return out
    return out


def _within_tolerance(claim: float, value: float, tolerance: float) -> bool:
    """Loose match — relative tolerance for non-tiny numbers, absolute
    tolerance for values near zero."""
    if abs(value) < 1.0:
        return abs(claim - value) <= max(tolerance, 0.5)  # absolute fallback
    return abs(claim - value) / abs(value) <= tolerance


def _normalised_unit(raw: str | None) -> str | None:
    if raw is None:
        return None
    u = raw.strip().lower()
    if u in _SIGMA_UNIT_TOKENS:
        return "sigma"
    if u in _PERCENT_UNIT_TOKENS:
        return "%"
    if u in _DAYS_UNIT_TOKENS:
        return "days"
    if u in _DOLLAR_UNIT_TOKENS or u.startswith("$"):
        return "$"
    return u


def _strict_pin_match(
    claim: float, unit: str | None, ctx_numerics: list[tuple[str, float]],
    tolerance: float,
) -> tuple[bool, bool, str | None]:
    """For unambiguous units, restrict matching to fields whose path
    suggests the same unit family.

    Returns ``(strict_attempted, matched, matched_path)``. When
    ``strict_attempted`` is True the caller must NOT fall back to the
    loose any-context-value match — sigma / % are unambiguous so a
    failed strict check is a violation.
    """
    if unit == "sigma":
        candidates = [
            v for path, v in ctx_numerics
            if any(token in path for token in ("_z", "current_z", "garch_z", "stretch", "zscore"))
        ]
        for v in candidates:
            if _within_tolerance(claim, v, tolerance):
                return True, True, "z-score family"
        # Sigma is signed; allow the negation match too.
        for v in candidates:
            if _within_tolerance(claim, -v, tolerance):
                return True, True, "z-score family (negated)"
        return True, False, None
    if unit == "%":
        # Percent claims may appear as "74" (the number) but the
        # context stores the value as a fraction (0.74). Normalise the
        # claim to a fraction by dividing by 100 when |claim| > 1, then
        # also try the raw value (some context fields are already in
        # percent — vol_*_pct / *_pctile etc.).
        candidates = [
            (path, v) for path, v in ctx_numerics
            if any(token in path for token in (
                "_pct", "percentile", "_rate", "win_rate", "hit_rate",
                "_pctile", "p_value", "ratio",
            ))
        ]
        normalised = claim / 100.0 if abs(claim) > 1.0 else claim
        for path, v in candidates:
            if _within_tolerance(normalised, v, tolerance):
                return True, True, path
            if _within_tolerance(claim, v, tolerance):
                return True, True, path
        return True, False, None
    return False, False, None  # no strict-pin attempted; fall through to loose match


def validate_thesis_claims(
    thesis: dict,
    context: dict,
    *,
    tolerance: float = 0.05,
) -> dict:
    """Scan the thesis's natural-language fields for numeric claims
    and verify each one against ``context``.

    Parameters
    ----------
    thesis
        The structured thesis dict (typically ``thesis.raw`` or
        ``thesis_dict_from_audit_log``). Validator inspects these
        free-text fields:
          - ``plain_english_headline``
          - ``thesis_summary``
          - ``key_drivers`` (list of strings)
          - ``invalidation_risks`` (list of strings)
          - ``reasoning_summary``
    context
        ``ThesisContext.to_dict()`` shape. Validator flattens to
        leaf numerics.
    tolerance
        Relative tolerance. Defaults to 5%. Numbers within
        ``tolerance`` of a context value are considered traceable.

    Returns
    -------
    dict
        ``{
          "verdict": "verified" | "unverified",
          "n_claims": int,
          "violations": [ClaimViolation-asdict, ...]
        }``
    """
    text_fields: list[tuple[str, str]] = []
    for fname in ("plain_english_headline", "thesis_summary", "reasoning_summary"):
        val = thesis.get(fname)
        if isinstance(val, str) and val.strip():
            text_fields.append((fname, val))
    for fname in ("key_drivers", "invalidation_risks"):
        items = thesis.get(fname) or []
        if isinstance(items, list):
            for i, item in enumerate(items):
                if isinstance(item, str) and item.strip():
                    text_fields.append((f"{fname}[{i}]", item))

    ctx_numerics = _flatten_context_numerics(context)

    violations: list[ClaimViolation] = []
    n_claims = 0

    for field, text in text_fields:
        for m in _NUMBER_PATTERN.finditer(text):
            try:
                claim = float(m.group("value"))
            except (TypeError, ValueError):
                continue
            unit = _normalised_unit(m.group("unit"))
            # Prefix `$` (e.g. "$108") sets a dollar unit even when no
            # suffix unit was matched.
            if unit is None and m.group("prefix") == "$":
                unit = "$"

            # Skip noise: tiny integers without units (year tokens, list
            # indices, conviction scores) are too noisy to validate
            # without false positives. We only flag a claim if it
            # carries a unit OR is large enough to plausibly be a
            # market figure.
            has_unit = unit is not None
            is_market_sized = abs(claim) >= 5.0
            if not has_unit and not is_market_sized:
                n_claims += 1
                continue

            # Strict pin first (sigma + % are unambiguous).
            strict_attempted, pin_ok, _pin_path = _strict_pin_match(
                claim, unit, ctx_numerics, tolerance
            )
            n_claims += 1
            if pin_ok:
                continue
            if strict_attempted:
                # Strict-pin units MUST NOT fall back to the loose
                # match — that's the whole point of being strict.
                start = max(0, m.start() - 20)
                end = min(len(text), m.end() + 20)
                snippet = text[start:end].replace("\n", " ")
                violations.append(
                    ClaimViolation(
                        field=field,
                        value=claim,
                        unit=unit,
                        snippet=snippet,
                        reason=(
                            f"{unit}-unit claim {claim} does not match any "
                            f"unit-compatible context field within ±{tolerance*100:.1f}%."
                        ),
                    )
                )
                continue

            # Loose match: any context value within tolerance.
            matched = any(
                _within_tolerance(claim, v, tolerance) for _, v in ctx_numerics
            )
            if matched:
                continue

            # No match — record the violation.
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 20)
            snippet = text[start:end].replace("\n", " ")
            violations.append(
                ClaimViolation(
                    field=field,
                    value=claim,
                    unit=unit,
                    snippet=snippet,
                    reason=(
                        f"Numeric claim {claim} (unit={unit or 'n/a'}) does "
                        f"not trace to any context value within ±{tolerance*100:.1f}%."
                    ),
                )
            )

    verdict = "verified" if not violations else "unverified"
    return {
        "verdict": verdict,
        "n_claims": n_claims,
        "violations": [
            {
                "field": v.field,
                "value": v.value,
                "unit": v.unit,
                "snippet": v.snippet,
                "reason": v.reason,
            }
            for v in violations
        ],
    }


__all__ = ["validate_thesis_claims", "ClaimViolation"]
