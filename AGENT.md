# Agent Notes

This repo uses a lightweight working loop.

## Working Defaults

- Prefer a live `NEXT.md` at the repo root as the active checklist.
- Keep `NEXT.md` uncommitted unless the user explicitly wants it versioned.
- Update `NEXT.md` in place as progress is made and new follow-up steps appear.
- Use checkboxes for done, next, and still-open items.
- If a repo also needs Claude compatibility, keep `CLAUDE.md` as a thin wrapper that points at `AGENT.md`.

## Validation Flow

- For use case #3, validate with real concert files and real output paths in the homedir.
- After splitting a concert, cycle each resulting song through use case #2 with the real song file.
- Keep the validation loop tied to the actual file layout the user will use.
- If the task is mostly search, source discovery, or broad comparison, pass the baton to a search-oriented web agent and bring the result back here for implementation.

## Commit Hygiene

- Commit code, docs, and tests separately from planning scratch files when practical.
- Preserve user edits and unrelated changes.
