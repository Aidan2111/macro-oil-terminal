"""Build-info schema."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BuildInfo(BaseModel):
    """Stamped at deploy time by the CD workflow."""

    sha: str = Field(..., description="Full git commit SHA")
    time: str = Field(..., description="ISO-8601 UTC deploy timestamp")
    region: str = Field(..., description="Azure region string")
    sha_short: str | None = Field(
        default=None, description="Short SHA for display"
    )
    workflow_run: str | int | None = Field(
        default=None, description="GitHub Actions run id"
    )
