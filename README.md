<div align="center">
<h1>Repotainer</h1>
</div>

Repotainer inventories a project, reports evidence of Python, uv, and Poetry workflows, and creates a baseline Dev Container setup.

## Generate a dev container scaffold

Run `repotainer` to scan and scaffold the current directory, or `repotainer ./my-project` to use another directory. From a development checkout, use `uv run repotainer` with the same arguments.

After the inventory counts, the command prints the full detection result, including source paths, declaration values, and any read diagnostics. This temporary terminal output is intended for checking what the detection rules find. [CLI evidence output](docs/designs/cli-evidence-output.md)

The command recommends Python and uv requests using evidence from the entire selected scan. It keeps a compatible exact Python pin or uses the project's supported ranges to select a version. If Python declarations conflict, `project.requires-python` has priority over `.python-version`. Unresolved ties offer a numbered choice in a terminal. Unattended runs warn and use `latest` for those ties. A detected tool without version evidence also uses `latest`. Repotainer generates the requests on the host without a Mise installation or network lookup. [Tool version resolution](docs/designs/tool-version-resolution.md)

The command writes `.devcontainer/devcontainer.json`, `.devcontainer/Dockerfile`, `.devcontainer/setup.sh`, and root `mise.toml` at the selected root. The `[tools]` table is empty when neither tool is detected. After scanning, an interactive run previews changes and asks separately before replacing existing Dev Container files or `mise.toml`. Declined groups and existing groups in unattended runs stay intact. The writer backs up approved originals before writing. If a write fails, it attempts to restore the originals, remove files it created, and report any backup needed for manual recovery. [Scaffold writes and recovery](docs/designs/tool-version-resolution.md#back-up-and-restore-approved-replacements)

Review the generated `mise.toml` before creating the Dev Container. At post-create, the setup script runs `mise install` from the project root. A successful Repotainer run confirms generation. If container setup reports that a requested release is unavailable, edit `mise.toml` to a compatible available version and retry setup.

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
