# Designs

Spec documents — one per feature. Each file is named `<feature>.md`.

A design doc is reviewable in 5 minutes and covers:

- What ships (UI, API, schema, infra)
- What tests (named, not hand-waved)
- What monitoring / alerting
- Rollback behavior
- Out of scope (YAGNI)

A design doc is produced from a brainstorm (`docs/brainstorms/<feature>.md`)
after the problem has been interrogated and the approach chosen. The plan
(`docs/plans/<feature>.md`) is produced from the design — bite-sized tasks
with complete code and tests-first.

See `docs/workflow.md` for the full process.
