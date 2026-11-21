# Feature designs

Read only the designs relevant to the task. Approval, implementation, and verification are separate; see [Development](../development.md#designs-and-decisions) for maintenance rules.

| Design | Updated | Components | Review status | Implementation state |
| --- | --- | --- | --- | --- |
| [Repository inspection](repository-inspection.md) | 2026-11-21 | CLI, path validation, and local Git status | Current source contract | Updated for inventory cutover |
| [Repository inventory](repository-inventory.md) | 2026-11-21 | Main command, scan boundary, Git status, ignore rules, file catalog | EGM Review completed on draft. Matcher and cutover resolutions accepted | Implemented and [verified locally](repository-inventory.md#implementation-verification) |
| [Repository evidence detection](repository-evidence-detection.md) | 2026-11-21 | Rule matching, declaration readers, tool evidence | Author: Suchi Pragya. Author-approved. All nine agreed EGM resolutions applied | Implemented and [verified locally](repository-evidence-detection.md#implementation-verification) |
| [Root command](root-command.md) | 2026-11-21 | Single Typer command, handler name and location | Author: Suchi Pragya; author-approved design; five-stage review resolved | Implemented and [verified locally](root-command.md#implementation-verification) |
| [Remove Zensical](remove-zensical.md) | 2026-11-21 | Developer documentation, tooling, publication workflow | Author: Suchi Pragya; author-approved; [five-stage review](remove-zensical.md#review-results-and-resolution) completed; both adopted wording findings addressed | Implemented; [verification](remove-zensical.md#implementation-verification) recorded |
