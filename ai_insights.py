"""Azure OpenAI-backed market commentary for the terminal.

The module is intentionally defensive: if the Azure OpenAI environment
variables aren't present, or the SDK isn't installed, or the call
raises, we return a deterministic "canned" commentary so the UI never
breaks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class InsightContext:
    latest_brent: float
    latest_wti: float
    latest_spread: float
    latest_z: float
    z_threshold: float
    current_inventory_bbls: float
    floor_bbls: float
    daily_depletion_bbls: float
    projected_floor_date: Optional[pd.Timestamp]
    r_squared: float
    jones_mbbl: float
    shadow_mbbl: float
    sanctioned_mbbl: float
    total_fleet_mbbl: float
    total_vessels: int

    def prompt_snapshot(self) -> str:
        proj = (
            self.projected_floor_date.strftime("%Y-%m-%d")
            if self.projected_floor_date is not None
            else "no breach within horizon"
        )
        return (
            "Oil desk market snapshot:\n"
            f"- Brent ${self.latest_brent:,.2f} / WTI ${self.latest_wti:,.2f}\n"
            f"- Brent-WTI spread ${self.latest_spread:,.2f} "
            f"(90d Z-score {self.latest_z:+.2f}, alert threshold \u00b1{self.z_threshold:.1f}\u03c3)\n"
            f"- Total US inventory {self.current_inventory_bbls/1e6:,.1f} Mbbl, "
            f"floor {self.floor_bbls/1e6:,.0f} Mbbl\n"
            f"- Daily depletion {self.daily_depletion_bbls/1e3:+,.1f} kbbl/d "
            f"(R\u00b2 {self.r_squared:.2f}), projected breach {proj}\n"
            f"- Fleet on water (total {self.total_fleet_mbbl:,.1f} Mbbl across "
            f"{self.total_vessels} tankers):\n"
            f"    Jones Act / Domestic: {self.jones_mbbl:,.1f} Mbbl\n"
            f"    Shadow Risk (Panama, Liberia, MI, Malta): {self.shadow_mbbl:,.1f} Mbbl\n"
            f"    Sanctioned (Russia, Iran, Venezuela): {self.sanctioned_mbbl:,.1f} Mbbl\n"
        )


SYSTEM_PROMPT = (
    "You are a senior oil trading analyst writing a short daily note for a "
    "portfolio manager. Be concrete and quantitative. Cite the Z-score, "
    "depletion rate, and fleet split explicitly. Avoid hedging language "
    "like 'could potentially'. No investment advice disclaimers — "
    "the PM already knows. Output must contain two sections exactly: "
    "'Commentary' (1 short paragraph, 3-5 sentences) and 'Risk observations' "
    "(exactly 3 bullet points, 1 sentence each, concrete)."
)


def _canned_commentary(ctx: InsightContext) -> str:
    """Rule-based fallback used when Azure OpenAI is unreachable."""
    z = ctx.latest_z
    signal = (
        f"ALERT — spread {z:+.2f}\u03c3 outside \u00b1{ctx.z_threshold:.1f}\u03c3 band"
        if abs(z) >= ctx.z_threshold
        else f"quiet — spread {z:+.2f}\u03c3 inside band"
    )
    if ctx.projected_floor_date is not None:
        breach = f"projected breach {ctx.projected_floor_date:%Y-%m-%d}"
    else:
        breach = "no floor breach in the forecast horizon"

    sanctioned_pct = (
        ctx.sanctioned_mbbl / ctx.total_fleet_mbbl * 100.0
        if ctx.total_fleet_mbbl
        else 0.0
    )
    shadow_pct = (
        ctx.shadow_mbbl / ctx.total_fleet_mbbl * 100.0
        if ctx.total_fleet_mbbl
        else 0.0
    )
    jones_pct = (
        ctx.jones_mbbl / ctx.total_fleet_mbbl * 100.0 if ctx.total_fleet_mbbl else 0.0
    )

    return (
        "### Commentary\n\n"
        f"Brent {ctx.latest_brent:,.2f} vs WTI {ctx.latest_wti:,.2f} with spread "
        f"{ctx.latest_spread:+.2f}; rolling Z-score is {z:+.2f}\u03c3 ({signal}). "
        f"Total inventory sits at {ctx.current_inventory_bbls/1e6:,.0f} Mbbl and is "
        f"drawing down at {ctx.daily_depletion_bbls/1e3:+,.0f} kbbl/d "
        f"(regression R\u00b2 {ctx.r_squared:.2f}), giving {breach}. "
        f"Fleet mix: {jones_pct:.0f}% Jones Act, {shadow_pct:.0f}% shadow, "
        f"{sanctioned_pct:.0f}% sanctioned.\n\n"
        "### Risk observations\n\n"
        f"- Spread dislocation risk: watch for rapid mean reversion if Z moves "
        f"toward zero from the current {z:+.2f}\u03c3.\n"
        f"- Inventory floor risk: at current draw the {ctx.floor_bbls/1e6:,.0f} Mbbl "
        f"floor is {('reached ' + ctx.projected_floor_date.strftime('%Y-%m-%d')) if ctx.projected_floor_date else 'not imminent'}.\n"
        f"- Sanctions exposure: {sanctioned_pct:.0f}% of water-borne cargo flies "
        f"sanctioned flags; monitor enforcement headlines for secondary risk.\n"
        "\n*Fallback mode — Azure OpenAI not configured or unreachable.*"
    )


def generate_commentary(ctx: InsightContext) -> str:
    """Return a markdown commentary string. Always returns something."""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_KEY")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

    if not endpoint or not api_key:
        return _canned_commentary(ctx)

    try:
        from openai import AzureOpenAI  # type: ignore
    except Exception:
        return _canned_commentary(ctx)

    try:
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        resp = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": ctx.prompt_snapshot()},
            ],
            max_completion_tokens=500,
            temperature=0.3,
        )
        msg = resp.choices[0].message.content or ""
        msg = msg.strip()
        if not msg:
            return _canned_commentary(ctx)
        return msg + "\n\n*Live — Azure OpenAI `" + deployment + "`*"
    except Exception as exc:  # pragma: no cover — network issues, auth, etc.
        return _canned_commentary(ctx) + f"\n\n<!-- Azure OpenAI error: {exc!r} -->"


__all__ = ["InsightContext", "generate_commentary"]
