# Remove Zensical from developer documentation

- Author: Suchi Pragya.
- Updated: 2026-11-21.
- Review status: finalized and author-approved; all five EGM review stages completed on 2026-11-21 with nine fresh reviewers. No confirmed blockers or implementation-readiness findings; both adopted wording findings addressed. See [review results and resolution](#review-results-and-resolution).
- Implementation state: Zensical configuration, local serving task, publication workflow, and obsolete output ignore rule removed on 2026-11-21. Developer Markdown retained; generated output preserved outside the checkout. Verification results are recorded below.
- Components: developer documentation, documentation tooling, documentation publication workflow.

## Overview

Keep `docs/` as repository-based development documentation and remove the Zensical tooling used to turn it into a website. Developers and agents should continue to use the [development guide](../development.md) and [design index](SITEMAP.md) through ordinary Markdown links.

The author intends to revisit a separate product website and end-user documentation after the tool reaches an MVP. Astro under a root-level `website/` directory is a future possibility, not a dependency or implementation commitment for this change.

## The Problem

Zensical was initially added to support a user-facing website. The current documentation instead supports development: shared practices, feature designs, implementation boundaries, and decisions. The author has chosen to maintain these documents as repository Markdown and does not consider the website tooling's maintenance cost justified for the current workflow.

Before removal, the setup consisted of `zensical.toml`, a local documentation task in `mise.toml`, `.github/workflows/docs.yml`, and rendering requirements in the development guide. Zensical was invoked through `uvx`, rather than declared as an application dependency in [pyproject.toml](../../pyproject.toml).

Removal gives up the rendered documentation preview and strict site-build validation. Markdown linting and link checks still matter: removing the renderer must not leave developers with broken navigation or instructions that require a deleted tool. These checks do not provide every validation or presentation feature of the renderer.

## Goals

- Remove repository configuration, tasks, and workflow execution that depend on Zensical, including the repository's documentation publication workflow.
- Preserve the existing developer documentation, its stable paths, and its Markdown navigation.
- Reconcile development instructions with the remaining tooling, retaining Markdown linting and checks for local links without requiring a site build.
- Keep documentation tooling changes independent of Python application behavior and dependencies.
- Leave future product pages and end-user documentation to a separate website effort after the MVP.

## Non-Goals

- Delete developer documentation or rewrite it for an end-user audience.
- Build an Astro site, create a `website/` scaffold, or select its dependencies, navigation, or deployment setup now.
- Change GitHub Pages settings, remove a hosted deployment, or re-enable hosting. The author will handle GitHub Pages separately.
- Uninstall shared tools or remove caches outside this repository.
- Change CLI behavior, repository inspection, Git-root semantics, or the MVP feature scope.

## Technical Plan

### Documentation stays in the repository

The README continues to route contributors to the development guide and design index. Existing development and feature documents stay at their current paths. Developers read them in their editor or the repository's Markdown viewer; there is no replacement documentation server, site generator, or publishing process in this change.

```text
README.md
  → docs/development.md       setup, tooling, checks
  → docs/designs/SITEMAP.md   feature design navigation
      → feature designs      requirements, decisions, evidence

Markdown changes → Markdown lint + local link inspection
```

### Remove the website tooling

Delete `zensical.toml` and `.github/workflows/docs.yml`. Remove only the `docs` task from `mise.toml`; preserve unrelated tools, tasks, environment settings, and hooks. Remove the obsolete MkDocs `/site` ignore entry from `.gitignore` after checking for local generated output, so the change does not silently expose existing build output for accidental inclusion. Any existing output must be handled explicitly during implementation; unrelated or unconfirmed local content must be preserved.

Before removal, Zensical was invoked through `uvx` and had no declared project dependency or matching entry in the inspected `pyproject.toml`, `uv.lock`, or `mise.lock`. No dependency or tool-lock changes were needed. Do not remove `uv`, which continues to support the Python project, or clear shared tool environments and caches.

### Reconcile instructions and preserve checks

Update the development guide to describe repository-based Markdown as the documentation format. Remove the rendering-check requirement, local server instructions, and descriptions of the deleted documentation workflow. Keep the existing Markdown lint command and the requirement to inspect local links when documentation changes.

The existing Prek configuration retains its Markdown lint hook, and the general CI workflow continues to run Prek. Inspection of those files found no dedicated local-link checker. Local link verification remains an explicit inspection of relative file targets and referenced headings, including the README, development guide, design index, and changed designs. This plan adds no dependency, checker script, hook, or CI job. Markdown lint must not be described as proof that links resolve.

This design records historical configuration as well as intended behavior. When implementation deletes files, replace links to those deleted files in this document with plain code paths and label the description as the pre-removal state. Keep the design and index status aligned with actual approval, implementation, and verification results. Historical mentions of Zensical may remain as rationale; executable invocations and active instructions requiring it must be removed.

### Publication and application boundaries

Deleting the documentation workflow stops that workflow from building and deploying on future matching repository events once the change reaches the relevant branch. It does not remove an already hosted site or change repository hosting settings. The author handles GitHub Pages separately.

Python interfaces, CLI output, repository inspection behavior, and runtime dependencies remain unchanged. A future Astro website would be designed independently under `website/` after the MVP; this removal creates no scaffold or hosting configuration for it.

## Alternatives Considered

### Keep Zensical and the documentation website

Retain the current configuration, local server task, rendering checks, and publication workflow. This preserves the rendered preview and website navigation without requiring a migration. A website could also make developer documentation easier to browse for contributors who prefer that format; developer-focused content alone does not make a site generator unsuitable.

The cost is continuing to maintain a renderer, navigation configuration, and publication workflow for documentation whose current purpose is repository development. The author has requested complete Zensical removal and approved a technical plan using Markdown navigation instead.

Rejected by author: the current documents serve development, while a product website and end-user documentation belong to a later effort. The author accepts losing the rendered preview and strict build checks through approval of the Overview, Goals, and Technical Plan.

### Stop publishing but keep Zensical for local previews

Delete the publication workflow while retaining the configuration and local serve task. This would preserve rendered browsing without publishing development documents and would avoid replacing the existing renderer's validation with manual inspection alone.

It would still require Zensical-specific configuration and development instructions. It offers value if contributors need the local preview, but that need has not been established in this discussion. This alternative was considered during drafting; it is not selected by the approved Technical Plan, which removes Zensical completely.

### Replace Zensical with Astro now

Build a root-level `website/` project immediately and move website responsibilities to it. This could establish the future location for product pages and end-user documentation in one change. It would also introduce another site's dependencies, content structure, build checks, and deployment decisions before the MVP establishes what users need documented.

Deferred by author: revisit a possible Astro website after the MVP. This change therefore removes the existing site tooling without introducing a replacement. The framework, content, and hosting design remain decisions for that future effort.

## Detailed Implementation Plan

### Delivery sequence and affected files (historical)

The following preserves the approved implementation sequence. It was executed on 2026-11-21; actual results are recorded under Implementation verification. The drafting baseline was HEAD `5230c15` on `docs/project-documentation-framework`, with this design and its index entry as uncommitted documentation changes. Recheck the branch, working tree, and worktree before any future changes.

1. Inspect the repository's Zensical references, including hidden configuration files, without reading secrets, private content, or shared caches. Confirm that the files below still contain all active integrations. If another integration has appeared, reconcile the plan before expanding the change.
2. Handle local generated output before removing its ignore rule. A real `site/` directory exists in the drafting checkout as of 2026-11-21; its contents have not been inspected or established as entirely generated. Confirm its provenance from build markers and filenames without reading unrelated content. If confirmed as generated output, move the directory intact to a newly created unique backup directory outside the repository, record the backup path, and retain it for the author. Do not delete its contents. If provenance remains uncertain, leave the directory and ignore rule in place and report that cleanup as unresolved rather than moving unconfirmed content. Check again at implementation time because local output may have changed.
3. Delete root `zensical.toml`. This removes the renderer's site metadata, theme, navigation, and Markdown extension settings. Preserve the Markdown source documents it previously referenced.
4. Delete `.github/workflows/docs.yml`. This removes the Zensical build, documentation artifact upload, and Pages deployment jobs together. Do not change GitHub repository settings, environments, or hosted deployments.
5. Modify [mise.toml](../../mise.toml) to remove the complete `[tasks.docs]` block, including its command and description. Preserve every other task, tool declaration, hook, and setting. Do not run the remaining tasks merely to verify this deletion; some change environments or upgrade dependencies.
6. Modify [.gitignore](../../.gitignore) to remove only the obsolete `# mkdocs documentation` comment and `/site` entry after step 2 establishes that doing so will not expose unhandled local content. Preserve unrelated ignore rules.
7. Modify [docs/development.md](../development.md) to state that `docs/` serves development through repository Markdown. Remove the documentation rendering row from the checks table, the Zensical and local server sentences, and the separate publication-workflow description. Preserve the Python formatting instructions in their existing paragraph and the description of general CI. Update the final documentation-maintenance paragraph to require Markdown and local-link checks without requiring rendering. Explicitly describe local-link inspection as a contributor check, not an enforced CI capability. Keep setup, dependency, hook, and application-test guidance unchanged.
8. Modify [docs/designs/remove-zensical.md](remove-zensical.md), this design, to describe the former configuration as historical and replace Markdown links to deleted files with code paths. Record implementation state, verification commands and results, the assessed revision or working-tree state, and any generated-output backup or unresolved cleanup. Preserve the approval history, alternatives, and future website boundary. Retain historical rationale mentioning Zensical; complete removal means removing active integration, not erasing the decision record.
9. Modify [docs/designs/SITEMAP.md](SITEMAP.md) to reflect the design's actual review and implementation state. Do not claim a Goldfish review, completed implementation, or passing verification unless it occurred.
10. Run the verification below, inspect the entire resulting diff including any hook or formatter edits, and report results and limitations. Leave the change uncommitted and unpushed unless separately requested.

No other tracked files are expected to change. In particular, `README.md`, `AGENTS.md`, `docs/designs/repository-inspection.md`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `pyproject.toml`, `uv.lock`, `requirements.txt`, and `mise.lock` remain unchanged. They are inspected where relevant to navigation, retained checks, and dependency boundaries. No application source, tests, checker scripts, website scaffold, or replacement configuration is created.

### Verification plan

- Run `rumdl check AGENTS.md README.md docs`, covering the design even if it is still untracked. Resolve issues only within the authorized change.
- Inspect relative file links and referenced headings in the README, agent instructions, development guide, design index, and both designs. Confirm that links to removed configuration or workflow files have been removed or converted to historical code paths. Markdown lint alone is not evidence that links resolve.
- Search tracked files and the new design for `zensical`, `mkdocs`, the removed task, and the deleted workflow path. Review each remaining match: historical explanations and removal instructions in this design are allowed; active tooling commands, required rendering checks, and links to deleted files are not.
- Parse the remaining `mise.toml` with Python's standard-library TOML reader. Confirm that its `docs` task is absent and its other configuration matches the baseline. Do not install dependencies or regenerate lockfiles for this configuration-only removal.
- Confirm the renderer configuration and documentation workflow are absent. Inspect the remaining CI and Prek configuration to confirm that general repository checks and Markdown lint remain configured. This inspection does not establish that remote CI has run successfully.
- Run `git diff --check` and inspect tracked and untracked changes. Confirm the expected file scope, unchanged application and lock files, and absence of newly exposed `site/` output. If hooks are run, inspect and reconcile their edits rather than accepting unrelated changes.
- Do not run Zensical after removal. Do not add or run application tests for this documentation/tooling change; no Python behavior changes. Existing Python checks remain available for future application changes.

### Contributor journeys and completion criteria

- Given a checkout with the removal applied, when a contributor follows the README's development and design links, the existing Markdown pages and relevant headings resolve without a site server or Zensical installation.
- Given a documentation edit, when a contributor follows the updated development guide, Markdown lint and local-link inspection can be performed without a renderer. The guide makes no claim that link checks run in CI.
- Given the updated repository on a matching branch, future pushes no longer have the deleted documentation workflow available to build or deploy. Taking down an existing site remains the author's separate action.
- Completion requires the specified repository integrations and stale instructions to be removed, local generated output to be accounted for, navigation to remain usable, and actual verification results to be recorded. Unresolved local-output cleanup must be reported rather than hidden behind a completed status.

### Draft verification evidence

During drafting and finalization, `rumdl check AGENTS.md README.md docs` and `git diff --check` passed. Relative Markdown file targets and heading references were checked in the README, agent instructions, development guide, design index, and both designs. The assessed state is HEAD `5230c15` with this design and its index entry as uncommitted documentation changes.

A strict documentation build was attempted for the opening draft but could not run: the sandbox prevented writes to default uv locations and then blocked access to `pypi.org` when temporary writable locations were used. No successful rendering result is claimed. These drafting checks do not verify the removal, which has not been implemented.

## Review results and resolution

All five EGM stages reviewed the pre-fix design at HEAD `5230c15` plus its uncommitted documentation changes. Nine fresh reviewers completed their assigned reviews. Initial Zoom Out, Comprehension, Intermediate Zoom Out, and Implementation Readiness added no new findings; the critic stage produced two adopted wording findings and two duplicate attribution objections that were not adopted. The six standalone review reports were deleted from the project root at the author's request on 2026-11-21; this section retains the review outcome.

On 2026-11-21, the author requested both wording fixes. A1 is addressed by framing the maintenance cost as the author's workflow judgment rather than claiming that the rendered site offers developers no value. A2 is addressed by removing the redundant final caveat from the local-preview alternative. No architecture, implementation steps, or scope changed. The duplicate objections D1/S1 were not adopted because they applied a restriction on unsupported upstream-maintainer attribution to the current author's own decisions; the drafting workflow permits recording those author decisions in the design.

These were author-authorized document corrections following the completed review, not a new independent re-audit. At correction time, removal was unimplemented and local generated output still required inspection. The subsequent implementation and its verification are recorded separately below.

## Implementation verification

Implemented on 2026-11-21 in the working tree based on HEAD `5230c15`, branch `docs/project-documentation-framework`. Deleted `zensical.toml` and `.github/workflows/docs.yml`, removed only the documentation task from `mise.toml`, removed the obsolete output ignore entry, and reconciled the development guide and design index. The standalone review artifacts were subsequently deleted at the author's request; the review outcome remains above.

All four HTML pages under the former `site/` directory contained a `zensical-0.1.3` generator marker; the remaining entries were stylesheet, script, image, search, sitemap, and license assets. No symlinks were present. The directory was moved intact to `/tmp/repotainer-zensical-site-icg_tw9y/site` before its ignore rule was removed. Nothing in that output was deleted; the backup is temporary local storage and is not versioned.

Verification performed:

- Markdown lint passed across the development documentation and all six review reports at implementation time. After the reports were deleted, `rumdl check AGENTS.md README.md docs` passed for the remaining documentation.
- Local navigation: relative file targets and heading references checked across the README, agent instructions, all documents under `docs/`, and all six review reports at implementation time. Links to deleted configuration and workflow files were converted to historical code paths. Links to the review reports were removed when those reports were deleted.
- Configuration: Python's standard-library TOML parser confirmed that `mise.toml` matches the HEAD configuration with only the `docs` task removed. Renderer configuration, documentation workflow, and local `site/` output are absent from the checkout.
- Preservation: byte comparisons against HEAD confirmed unchanged `pyproject.toml`, `uv.lock`, `mise.lock`, `requirements.txt`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `README.md`, `AGENTS.md`, and the repository-inspection design. The retained hook configuration still includes Markdown lint; general CI still invokes Prek.
- Reference inspection: no active Zensical integration, MkDocs output ignore entry, local serve task, or required rendering check remains. Mentions in this design and review artifacts describe the removed setup, alternatives, or historical verification.
- Diff: `git diff --check` passed; implementation changes are limited to the seven planned paths, alongside the previously created review reports. No formatter or hook modifications occurred.

Application tests, Python lint/type checks, and a renderer build were not run for this documentation/tooling removal. No Python source or runtime dependencies changed, no replacement renderer was added, and the removed renderer is no longer a required check. Remote CI and hosted-site removal are not verified here; GitHub Pages administration remains with the author. No commit or push was performed.

## Drafting context

This design uses the author's discussion in the current chat: remove Zensical, keep `docs/` for development, defer a possible Astro website until after the MVP, and leave GitHub Pages administration to the author. No predecessor concepts brief was created. The author approved the Overview and Goals, Technical Plan, Alternatives, and Detailed Implementation Plan in sequence, then requested finalization at the existing design location. The finalized design preserves that scope; it introduces no replacement dependency, application interface change, or website architecture. Design approval and finalization do not constitute implementation or successful implementation verification.

*Drafted with EGM.*
