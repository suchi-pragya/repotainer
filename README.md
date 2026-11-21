<div align="center">
<h1>Repotainer</h1>
</div>

Repotainer aims to generate reproducible Dev Container configurations from repository files. The current milestone inventories a directory and reports the number of retained files, retained directories, and skipped directory trees.

## Inventory a project

Run `repotainer` to scan the current directory, or `repotainer ./my-project` to use another directory. From a development checkout, use `uv run repotainer` with the same arguments.

The scan works with or without Git installed. It applies supported `.gitignore` rules within the selected directory, skips symlinks and built-in exclusions such as `.venv` and `node_modules`, and asks before retaining more than 1,000 entries. Run `repotainer --help` for command usage. See [Repository inventory](docs/designs/repository-inventory.md) for the supported ignore syntax and scan boundaries.

## Quick Start (Dev Container)

Prerequisites: Docker + VS Code with the Dev Containers extension.

```bash
# Clone the template
git clone https://github.com/suchi-pragya/repotainer.git

# Enter the project folder
cd repotainer

# Open in VS Code
code .
```

Then run: `Dev Containers: Reopen in Container` from the VS Code Command Palette.

## Documentation

Read [Development](docs/development.md) for setup, tooling, and checks, and the [design index](docs/designs/SITEMAP.md) for feature architecture and decisions. Agents should read [AGENTS.md](AGENTS.md) before working on the project.
