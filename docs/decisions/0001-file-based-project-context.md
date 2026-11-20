# 0001: File-based project context

- Date: 2026-10-23
- Status: accepted
- Agreement: user requested repository documentation and agent instructions on 2026-10-23
- Supersedes / superseded by: none

## Context

Repotainer is developed solo across multiple agent conversations. Future sessions need the design and decision rationale without relying on complete conversation histories. Keeping documentation creates maintenance work, so it must remain small.

## Decision and rationale

Preserve important technical context alongside the source and use a short `AGENTS.md` as the entry point. Conversation history remains supporting material. A custom durable agent platform is unnecessary for the current need.

The user explicitly requested simplifying the initial framework to reduce bookkeeping. Keep architecture, contributing instructions, and ADRs; add other categories only when real content warrants them. Agents update affected documentation as part of their work, without requiring a separate user reminder.

## Consequences

Design and reasoning remain available across sessions. There are no mandatory journals, progress reports, task records, or proposal folders. Significant future designs can use proposed ADRs. Documentation still needs review against source; file persistence alone does not ensure accuracy.

## Implementation and evidence

The framework is maintained on `docs/project-documentation-framework`. See the [document map](../index.md). No agent persistence service or Python behavior change is introduced.
