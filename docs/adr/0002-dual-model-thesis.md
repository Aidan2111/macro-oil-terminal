# ADR 0002: Dual-model Trade Thesis (fast + reasoning)

* Status: accepted
* Date: 2026-04-22
* Deciders: @Aidan2111

## Context

Tab 4 generates a structured trade thesis via Azure OpenAI. The first
version used a single deployment (`gpt-4o-mini`) for every call —
consistent latency but shallow "thinking" on complex regimes.

Two real user patterns emerged:

1. "I'm clicking through the dashboard, just want a quick read." — wants
   a thesis in < 3s, doesn't care about reasoning depth.
2. "The spread just blew out to 3σ with Cushing draining — *think hard*
   before giving me a view." — wants more deliberation, accepts 15–20s.

A single deployment can't serve both without either being too slow for
case 1 or too shallow for case 2.

## Decision

Provision **two** Azure OpenAI deployments on the same account
(`oil-tracker-aoai`, RG `oil-price-tracker`):

- `gpt-4o` (GlobalStandard, cap 50) — "Quick read" mode, ~2–10s.
- `o4-mini` (GlobalStandard, cap 50) — "Deep analysis" reasoning mode,
  10–20s, exposes a `reasoning_summary` field.

Tab 4 has a mode radio. Env vars map modes → deployments:

```
AZURE_OPENAI_DEPLOYMENT_FAST=gpt-4o
AZURE_OPENAI_DEPLOYMENT_DEEP=o4-mini
```

Reasoning models require API version `2024-12-01-preview` or later;
`trade_thesis._call_azure_openai` auto-upgrades to `2025-04-01-preview`
when a deployment name starts with `o1/o3/o4` and skips the
`temperature` kwarg (reasoning models reject it).

Streaming is enabled by default; on stream error we fall back to sync
and append a `retried` flag to the audit log.

## Consequences

**Positive:**

- User picks the latency/depth trade-off per call.
- Reasoning summary is a useful second-order artifact for audit.
- Fast mode stays cheap; deep mode is rate-limited at 30/hour/session.

**Negative / trade-offs:**

- Two deployments to maintain + rotate keys on.
- API version pinning is per-call, not global — makes the
  troubleshooting matrix a little wider ("Did you test it on version X?").
- Cost: deep mode burns ~5-10x tokens per call. Bucketed alerts cover it.

## Alternatives considered

- **Single deployment with `temperature`/`max_tokens` variations** —
  rejected, doesn't recover the quality lift of a reasoning model.
- **Function-call to an external reasoning chain** — rejected, added
  plumbing without commensurate benefit vs a second Azure deployment.

## References

- Commit `5ec0b27` — `feat(thesis): upgraded models + streaming + materiality + history + dual-mode UI`
- `docs/ai_trade_thesis.md` — system prompt and schema details
