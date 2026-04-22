# Development Workflow

This project follows a **Superpowers-inspired workflow** for any change larger
than a typo fix: brainstorm → design → worktree → plan → TDD → review → finish.

> The methodology itself is documented in the Superpowers plugin (Claude Code,
> via the official plugin marketplace: `/plugin install superpowers@claude-plugins-official`).
> This page describes how we apply it here — not every team member runs
> Claude Code, so the workflow is expressed in plain terms that anyone can
> follow by hand.

## The flow at a glance

```
┌──────────────┐   ┌────────┐   ┌──────────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌────────┐
│ brainstorm   │ → │ design │ → │ worktree │ → │ plan │ → │ TDD  │ → │review│ → │ finish │
│  (rough)     │   │ (spec) │   │  (iso)   │   │(tasks│   │(r→g→r│   │(per  │   │(merge/ │
│              │   │        │   │          │   │ 2-5m)│   │ -ref)│   │ task)│   │  PR)   │
└──────────────┘   └────────┘   └──────────┘   └──────┘   └──────┘   └──────┘   └────────┘
      ↓               ↓              ↓            ↓          ↓          ↓           ↓
 docs/brainstorms  docs/designs  .worktrees/  docs/plans  red-green  by fresh    base
                                  or sibling              -refactor  reviewer    branch
```

## 1. Brainstorm — `docs/brainstorms/<feature>.md`

Before writing code, restate the user problem and interrogate it. This is
Socratic — one question at a time, in chunks short enough to actually read.
Cover:

- What are users actually trying to do? What decision are they making?
- What alternatives were considered? (a tab, a banner, a separate mode…)
- Why is the chosen approach better than the alternatives?
- What assumptions are we making? What's unknown?
- What would prove the idea wrong?

Exit criterion: a brainstorm doc that a teammate can read in 5 minutes and
disagree with specifically.

## 2. Design — `docs/designs/<feature>.md`

The brainstorm becomes a spec. Reviewable in 5 minutes. Must cover:

- What ships (UI changes, API changes, schema changes)
- What tests (unit, integration, e2e) — named, not hand-waved
- What monitoring / alerting
- What rolls back cleanly and what doesn't
- Out of scope (YAGNI)

Exit criterion: a teammate can implement the feature from the spec alone
without asking clarifying questions.

## 3. Worktree — isolated branch, clean baseline

```bash
# Preferred: sibling directory (out of repo tree)
git worktree add ../macro_oil_terminal-<feature> <feature>

# OR: in-repo hidden dir (.gitignored)
git worktree add .worktrees/<feature> -b <feature>
```

Run the full test baseline in the worktree BEFORE writing any code.
If tests aren't green, that's a pre-existing problem — flag it, don't
pile new work on top.

```bash
cd ../macro_oil_terminal-<feature>
python test_runner.py   # expect all green
pytest                   # expect all green
```

## 4. Plan — `docs/plans/<feature>.md`

Break the spec into **2–5 minute tasks**. Every task has:

- Exact file paths (no "the UI layer")
- Complete code (no "add appropriate error handling")
- A test that goes first
- A verification command with expected output
- A commit message

No placeholders. If you write "TBD", the plan isn't done.

## 5. TDD — red / green / refactor, per task

Non-negotiable order for every task:

1. **Red** — write the failing test. Run it. Watch it fail for the expected reason.
2. **Green** — write the minimum code to make it pass. Run it. Watch it pass.
3. **Refactor** — clean up WHILE tests stay green.
4. **Commit** — small, focused, describes behavior.

If you wrote code before the test, delete the code. Start over. No exceptions.

## 6. Review — per task, not just at the end

After each task:

- Read the diff cold. Does it match the plan?
- Any dead code, magic numbers, copy-paste, inconsistent naming?
- Any test that passes without exercising the new behavior?
- Any requirement from the spec that isn't covered?

Critical issues block progress. Fix them before the next task.

When an agent is driving, a fresh subagent per task gives clean-context
review — that's the Superpowers default. When a human is driving, a quick
self-review diff read is the baseline; for bigger changes, ask a teammate.

## 7. Finish — `finishing-a-development-branch`

When all plan tasks are green:

1. Run the full test suite on the branch. Real command, fresh output.
2. Pick one of:
   - **Merge to main locally** (trunk-based — our default)
   - **Push and open a PR** (for bigger or risker changes)
   - **Keep the branch** (not done yet; coming back later)
   - **Discard** (we changed our minds — requires typed confirmation)
3. Clean up the worktree.

After merge: watch CI + CD. A push to `main` deploys to Azure. Don't walk
away until the health check is green.

## Directory conventions

| Path                 | Holds                                                     |
| -------------------- | --------------------------------------------------------- |
| `docs/brainstorms/`  | Rough problem explorations and alternatives considered    |
| `docs/designs/`      | Spec docs, reviewable in 5 minutes                        |
| `docs/plans/`        | Implementation plans, bite-sized tasks                    |
| `docs/adr/`          | Architecture decision records (already in use)            |
| `.worktrees/`        | In-repo worktrees (gitignored)                            |

## Why this, why now

The project has gone through several big pivots under time pressure and the
failure mode has consistently been: code written before a test, features
scoped ambiguously, last-minute reviews against an invisible spec. The
Superpowers workflow slows the first 20% down and removes the last 80% of
thrashing. See `docs/brainstorms/` and `docs/plans/` for any in-flight work.

## When to skip

This workflow is overkill for:

- Typo fixes
- Dependency bumps handled by Dependabot
- Documentation-only changes
- Log message tweaks

Everything else — features, bug fixes with any ambiguity, refactoring,
schema changes — goes through the full flow.
