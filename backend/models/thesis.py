"""Thesis schema — stub.

Phase 4 grows this into the full `Thesis` shape (stance, confidence,
plain_english_headline, instruments[], checklist[]).
"""

from __future__ import annotations

from pydantic import BaseModel


class ThesisStub(BaseModel):
    """Placeholder thesis schema."""

    status: str
    message: str
