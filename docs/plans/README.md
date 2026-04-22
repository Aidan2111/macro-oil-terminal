# Plans

Implementation plans — one per feature. Each file is named `<feature>.md`.

A plan doc breaks a design (`docs/designs/<feature>.md`) into **2–5 minute
tasks**. Every task has:

- Exact file paths (no "the UI layer")
- Complete code (no "add appropriate error handling")
- A test that goes first
- A verification command with expected output
- A commit message

No placeholders. If a task contains "TBD", the plan isn't done.

Plans drive TDD execution: red (write failing test) → green (minimum code)
→ refactor → commit. Every task has a test that goes first.

See `docs/workflow.md` for the full process.
