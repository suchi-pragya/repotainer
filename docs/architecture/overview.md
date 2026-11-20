# Implemented architecture

Baseline inspected on 2026-10-23 at revision `d2970399fb7c34e447e15d81c024c14c8afd648b`. Update this description when responsibilities or observable behavior change. Git history preserves earlier descriptions.

## Entry points and responsibilities

| Component             | Responsibility                                                       | Source                                  |
| --------------------- | -------------------------------------------------------------------- | --------------------------------------- |
| Installed command     | Maps `repotainer` to `repotainer.cli:main`                           | `pyproject.toml`                        |
| CLI composition       | Creates the Typer app and registers commands                         | `src/repotainer/cli.py`                 |
| Detect command        | Accepts input, invokes inspection, renders context and errors        | `src/repotainer/commands/detect.py`     |
| Repository inspection | Builds `RepositoryContext` and searches for Git markers              | `src/repotainer/scanning/repository.py` |
| Path classification   | Expands `~`, resolves an existing path, identifies file or directory | `src/repotainer/scanning/paths.py`      |

Source paths are relative to the repository root; inspect the current source before editing.

## Current behavior

The command defaults to the working directory. A directory is its own scan root; a file uses its parent directory. Git discovery searches the scan root and its ancestors for a `.git` directory or file. This is marker discovery, not validation through Git.

If no Git root is found, the command exits with code 2 unless `--allow-no-git` is supplied. Invalid or unsupported paths also produce an error with code 2. Successful output reports context only.

The distinction between the selected scan root and an ancestor Git root is unresolved. Existing behavior is not evidence that the user has accepted those semantics.

## Verification and missing components

`tests/test_repository.py` covers ancestor Git discovery for a nested file, `.git` file markers, and the no-Git override. Run the tests to establish their result for the current checkout.

Repository inventory, requirement detection, configuration planning, and configuration generation are not implemented. Use proposed ADRs for significant design choices before describing their implementations here.

## Open design questions

- Should a selected directory without its own `.git` warn even if an ancestor is a Git repository? Resolve this with the user before changing behavior.
- Which ecosystems and inferred requirements should the first useful release support?
- What evidence will demonstrate the correctness and usefulness of generated configurations? No comparative results have been established.
