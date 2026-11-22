# Feature designs

Read only the designs relevant to the task. Approval, implementation, and verification are separate; see [Development](../development.md#designs-and-decisions) for maintenance rules.

| Design | Updated | Components | Review status | Implementation state |
| --- | --- | --- | --- | --- |
| [Mise tool configuration from repository evidence](mise-tool-configuration.md) | 2026-11-22 | Python and uv detection, generated `mise.toml` | Approved by Suchi Pragya. All ten EGM review findings resolved | Implemented and [verified locally](mise-tool-configuration.md#implementation-verification) |
| [Dev container scaffold generation](devcontainer-scaffold.md) | 2026-11-22 | Root command, dev container templates, `mise.toml`, destination conflicts | Approved by Suchi Pragya. All 12 EGM review findings resolved | Implemented and [verified locally](devcontainer-scaffold.md#implementation-verification) |
| [Repository inspection](repository-inspection.md) | 2026-11-22 | CLI, path validation, local Git status, and scaffold generation | Current source contract | Updated for scaffold generation |
| [Repository inventory](repository-inventory.md) | 2026-11-21 | Main command, scan boundary, Git status, ignore rules, file catalog | EGM Review completed on draft. Matcher and cutover resolutions accepted | Implemented and [verified locally](repository-inventory.md#implementation-verification) |
| [Repository evidence detection](repository-evidence-detection.md) | 2026-11-21 | Rule matching, declaration readers, tool evidence | Author: Suchi Pragya. Author-approved. All nine agreed EGM resolutions applied | Implemented and [verified locally](repository-evidence-detection.md#implementation-verification) |
| [Built-in detection rules](built-in-detection-rules.md) | 2026-11-21 | Tool-specific rule modules, registry, evidence sharing across tools | Author: Suchi Pragya. Author-approved design. All eight EGM review findings resolved | Implemented and [verified locally](built-in-detection-rules.md#implementation-verification) |
| [CLI evidence output](cli-evidence-output.md) | 2026-11-21 | Root command, detector handoff, terminal output | Author Suchi Pragya. Author-approved design. All 11 EGM review findings resolved | Implemented and [verified locally](cli-evidence-output.md#implementation-verification) |
| [Root command](root-command.md) | 2026-11-21 | Single Typer command, handler name and location | Author: Suchi Pragya; author-approved design; five-stage review resolved | Implemented and [verified locally](root-command.md#implementation-verification) |
| [Remove Zensical](remove-zensical.md) | 2026-11-21 | Developer documentation, tooling, publication workflow | Author: Suchi Pragya; author-approved; [five-stage review](remove-zensical.md#review-results-and-resolution) completed; both adopted wording findings addressed | Implemented; [verification](remove-zensical.md#implementation-verification) recorded |
