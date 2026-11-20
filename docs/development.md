# Development

This is the shared development authority for humans and agents. The repository-root `AGENTS.md` defines agent operating boundaries; the [design index](designs/SITEMAP.md) routes readers to feature architecture and decisions. Run all commands below from the repository root unless stated otherwise.

## Environment and dependencies

Python requirements and the installed `repotainer` entry point are defined in [pyproject.toml](../pyproject.toml); [.python-version](../.python-version) selects the development interpreter. [uv.lock](../uv.lock) owns resolved Python dependencies. [mise.toml](../mise.toml) declares development tools and tasks; [mise.lock](../mise.lock) records tool resolutions. Configuration owns exact versions and task bodies.

For the Dev Container route, install Docker, VS Code, and its Dev Containers extension, open the checkout, and select **Dev Containers: Reopen in Container**. The [container configuration](../.devcontainer/devcontainer.json) uses the [Dockerfile](../.devcontainer/Dockerfile) and runs `bash scripts/setup.sh` after creation. That script trusts mise configuration and installs its declared tools; it does not sync project dependencies itself.

For a host setup, install and activate mise in Bash or Zsh, then run:

```bash
mise trust mise.toml
mise install
```

These commands change local trust and tool installation state. Review configuration before trusting it. The configured shell-entry hook runs [scripts/enter_project.sh](../scripts/enter_project.sh): it can install Commitizen with uv and install or overwrite Git hooks using Prek. Its Windows hook is empty. Setup documentation does not establish that this hook has run on a particular machine.

In either environment, sync the locked dependencies, then check the CLI:

```bash
uv sync --locked
uv run repotainer --help
```

`uv sync --locked` creates or updates `.venv` without updating the lockfile. Bash and Zsh users can optionally activate it with `source .venv/bin/activate`; `uv run` does not require activation. `uv run` may sync the environment before executing its command.

Use `uv add <package>` or `uv remove <package>` for an authorized dependency change; these modify project metadata and the lockfile. The configured `mise run sync` task runs `uv sync --upgrade`, which can upgrade dependencies and rewrite `uv.lock`; it is not the locked setup command. The uv export hook regenerates [requirements.txt](../requirements.txt) from project dependency metadata; do not treat that export as an independent dependency authority.

To use the checkout's CLI from other directories, run `mise run install-cli` here. This runs `uv tool install --editable .` and changes your user tool environment. If the executable is unavailable afterward, run `uv tool update-shell` and reopen the terminal.

## Checks

Run checks appropriate to the change. Commands in this table check project files without intentionally fixing them; tools may create caches, environments, or build output.

| Purpose | Command | Configuration and scope |
| --- | --- | --- |
| Python behavior | `uv run python -m unittest discover -s tests` | Run for Python behavior changes; tests live in `tests/`. |
| Python lint | `ruff check .` | Rules in [ruff.toml](../ruff.toml); relevant for Python edits. |
| Python formatting | `ruff format --check .` | Formatting in `ruff.toml`; relevant for Python edits. |
| Python types | `ty check` | Type checker also configured as a hook; relevant for Python edits. |
| Dependency lock | `uv lock --check` | Checks consistency with `pyproject.toml`. |
| Markdown | `rumdl check AGENTS.md README.md docs` | [rumdl.toml](../rumdl.toml); required for Markdown changes, including new files. |
| Documentation rendering | `uvx zensical build --strict` | [zensical.toml](../zensical.toml); required for documentation/navigation changes, writes ignored `site/` output. |
| Shell lint | `shellcheck scripts/*.sh` | Required for shell-script changes; mise supplies ShellCheck on Linux/macOS. |

Use `ruff check --fix .` and `ruff format .` only when intending to modify Python files, then inspect their diffs. `uvx` obtains Zensical separately from project dependencies; its version is not pinned in this repository. For a local documentation server, `mise run docs` runs `uvx zensical serve` and writes build output.

### Hooks and CI

Prek is already adopted in [mise.toml](../mise.toml) and [CI](../.github/workflows/ci.yml); [.pre-commit-config.yaml](../.pre-commit-config.yaml) defines its hooks. To install hooks explicitly, use `prek install` and `prek install --hook-type commit-msg`. These modify local Git hooks. Commitizen checks commit messages at the `commit-msg` stage; installing or passing hooks does not authorize a commit.

`prek run --all-files` runs pre-commit-stage checks across tracked files. Hooks include file/configuration sanity checks, private-key detection, whitespace fixes, uv lock validation/export, Ruff fixes/formatting, ty, rumdl, and ShellCheck. This command can modify files, including generated requirements and formatting. Inspect those changes, rerun failed checks, and do not bypass required hooks. For new files not yet tracked, use direct checks above or `prek run --files <paths>` with explicit paths rather than relying on `--all-files` coverage.

The repository CI workflow invokes Prek across tracked files. It does not explicitly run the unittest suite or documentation build. The separate [documentation workflow](../.github/workflows/docs.yml) runs `uvx zensical build --clean`, uploads an artifact on matching pushes, and deploys GitHub Pages. Its path filters cover `docs/**`, its workflow file, and `zensical.toml`; README-only or AGENTS-only changes do not trigger it. Local strict rendering remains a separate check. CI configuration is not evidence of a successful current run.

Gitleaks is declared as a mise tool but has no configured hook or CI invocation here. Do not describe it as an enforced check. [.editorconfig](../.editorconfig) sets whitespace defaults; for Markdown, keep each prose paragraph on one source line despite its general line-length hint. rumdl disables its line-length rule. Preserve structural line breaks in code, tables, lists, and quotations.

## Developing a change

Read the affected design, source, tests, and configuration before editing. Keep `src/repotainer/cli.py` focused on composition, commands in `commands/`, and domain behavior in the appropriate package. Preserve unrelated work and accepted requirements. Resolve material disagreements between documentation and implementation explicitly; observed code alone does not establish intended behavior.

Use existing designs for small changes. For substantial or uncertain choices, develop the owning feature design before consequential implementation. Run relevant checks, inspect resulting diffs, and reconcile affected documentation in the same change. Report actual verification and meaningful limitations; do not execute unrelated application tests merely for documentation setup.

## Designs and decisions

Store real feature designs directly in [designs/](designs/SITEMAP.md) with stable, descriptive filenames. Each design owns requirements, architectural responsibilities, interfaces, alternatives, significant decisions and rationale, consequences, open questions, and verification criteria. Register its status in the index and within the design. A reconstructed description of source is not an approved specification; record acceptance separately from implementation and verification.

Put significant choices in their owning design and link to those sections from dependent designs. No separate ADR collection or particular planning plugin is required. Do not invent agreement or rationale. Update an existing design for ordinary amendments; create another only when concrete scope needs independent discussion. Retain useful superseded designs at stable paths, marking their replacement explicitly rather than moving them because implementation finished. Implementation plans can be embedded or linked; label completed delivery steps as historical.

Keep useful verification evidence with its design, identifying its assessed revision or source state. Plans and test coverage are not successful execution results. Future changes must recheck relevant behavior instead of inheriting old verification claims.

## Documentation maintenance

The README introduces the product; this guide owns shared development practices; AGENTS owns agent permissions and reading routes; designs own feature architecture and decisions. Keep one authoritative home for each fact. File-based context preserves useful reasoning across conversations without requiring a durable agent service, journals, parallel status reports, or transcripts; persistence alone does not establish accuracy.

Update affected documents as part of implementation without a separate reminder. Assess behavior, interface, dependency, setup, tooling, and rationale changes. Distinguish stale prose, defects, unfinished work, and proposed behavior; do not rewrite accepted intent merely to match a defect. Routine fixes need no new document. Add pages or folders only for concrete content, maintain design status and navigation, and check local links plus the relevant Markdown and rendering checks. Tooling checks and scaffolding alone establish neither factual completeness nor safe unattended execution.
