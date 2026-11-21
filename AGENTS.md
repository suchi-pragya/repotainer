# Working on Repotainer

## Read by relevance

- Give concise, direct responses. Preserve the user's meaning and authorship.
- Read [Development](docs/development.md) for shared practices, tooling, checks, and documentation maintenance.
- Use the [design index](docs/designs/SITEMAP.md) to select relevant designs, then inspect the affected source and tests. Do not load the entire documentation tree.
- Read the [current-state design](docs/designs/repository-inspection.md) for implementation interfaces, invariants, and side effects.
- Read [Repository inventory](docs/designs/repository-inventory.md#choose-the-scan-root) for the intended scan boundary and Git status behavior before changing the current CLI.

## Operating boundaries

- Verify documentation against the current source and working tree. Surface disagreements; current behavior is not automatically the intended design.
- Distinguish proposed choices, accepted decisions, implemented behavior, and verified results. A suggestion is not approval.
- Never commit or push without an explicit request. Keep unrelated changes untouched.
- Stay within the authorized task. Documentation setup does not authorize feature implementation, publication, deployment, external communication, automation, or expanded execution permissions.
- Do not inspect secrets or private content to fill documentation gaps. Written instructions do not enforce sandbox isolation.
- Follow existing Python filesystem handling. Do not introduce shell commands for repository scanning without an agreed reason.

## Completion

Update affected documentation alongside relevant changes without waiting for a separate reminder. Follow the [development and verification guidance](docs/development.md#checks), inspect any formatter or hook edits, and report actual results and remaining uncertainty. Scaffolding alone does not establish factual completeness or safe unattended execution.
