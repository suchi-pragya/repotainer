<div align="center">
<h1>Repotainer</h1>
</div>

Repotainer inventories a project, reports evidence of Python, uv, and Poetry workflows, and creates a baseline Dev Container setup.

## Generate a dev container scaffold

Run `repotainer` to scan and scaffold the current directory, or `repotainer ./my-project` to use another directory. From a development checkout, use `uv run repotainer` with the same arguments.

After the inventory counts, the command prints the full detection result, including source paths, declaration values, and any read diagnostics. This temporary terminal output is intended for checking what the detection rules find. [CLI evidence output](docs/designs/cli-evidence-output.md)

The command creates `.devcontainer/devcontainer.json`, `.devcontainer/Dockerfile`, and `.devcontainer/setup.sh` in the target. If the project has no mise configuration of its own, Repotainer also creates `mise.toml` with an empty `[tools]` table. Existing project mise config is preserved. When a dev container runner creates the container, it runs the setup script, which calls `mise install` from the project root.

Existing dev container destinations or alternate configs stop generation. Repotainer lists the conflicts without creating any files. If a write fails, it attempts to clean up files created during that run and reports anything it could not remove. Inspect the reported paths before removing partial output and retrying. [Scaffold design](docs/designs/devcontainer-scaffold.md#destination-checks-and-writes)

The scan works with or without Git installed. It applies supported `.gitignore` rules within the selected directory, skips symlinks and built-in exclusions such as `.venv` and `node_modules`, and asks before retaining more than 1,000 entries. Run `repotainer --help` for command usage. See [Repository inventory](docs/designs/repository-inventory.md) for the supported ignore syntax and scan boundaries.

## Develop Repotainer in its dev container

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
