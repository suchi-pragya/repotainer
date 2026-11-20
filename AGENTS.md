# Working on Repotainer

## Start here

- Give concise, direct responses. Preserve the user's meaning and authorship.
- Read [the document map](docs/index.md), then only the architecture, decisions, and source relevant to the task. Do not load the entire documentation tree.
- Verify documentation against the current source and working tree. Surface disagreements; current behavior is not automatically the intended design.
- Distinguish proposed choices, accepted decisions, implemented behavior, and verified results. A suggestion is not approval.
- Never commit or push without an explicit request. Keep unrelated changes untouched.

## Development

- Keep `src/repotainer/cli.py` focused on composition, commands in `commands/`, and domain behavior in the appropriate package.
- Follow existing Python filesystem handling. Do not introduce shell commands for repository scanning without an agreed reason.
- Git-root selection is unresolved; see [architecture](docs/architecture/overview.md) before changing its semantics.
- Setup and environment instructions: [Contributing](docs/contributing/index.md).
- Run checks appropriate to the change: `uv run python -m unittest discover -s tests` for Python behavior, `rumdl check AGENTS.md README.md docs` for Markdown, and `uvx zensical build --strict` for documentation rendering.

## Maintain documentation as part of the work

- Update affected docs alongside relevant changes without waiting for a separate reminder. Routine fixes need no new document.
- Update [architecture](docs/architecture/overview.md) when component responsibilities, interfaces, or observable behavior change. Keep it about the current design; mark open questions explicitly.
- Record significant choices and their reasoning in [ADRs](docs/decisions/index.md). Include useful alternatives and supporting evidence; never invent rationale or assume user agreement.
- Update contributing instructions when setup or required checks change.
- Keep useful verification evidence with the relevant design or decision. Do not maintain parallel status reports, journals, or transcripts.
- Add a new document or folder only when concrete content needs it. Keep one authoritative home for each fact and link to it elsewhere.
