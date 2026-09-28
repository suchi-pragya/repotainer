# Contributing

## Clone the repository

You need Git. For the Dev Container setup, you also need Docker, VS Code, and the Dev Containers extension.

```bash
git clone https://github.com/suchi-pragya/repotainer.git
cd repotainer
```

## Set up the development environment

Open the checkout in VS Code with `code .`, then select **Dev Containers: Reopen in Container** from the Command Palette. The container runs `scripts/setup.sh` to trust the project configuration and install the tools declared in `mise.toml`.

To work without the container, install and activate mise in your shell, then run these commands from the checkout:

```bash
mise trust mise.toml
mise install
```

In either environment, sync the project and activate its virtual environment (Bash or Zsh):

```bash
uv sync --locked
source .venv/bin/activate
repotainer --help
```

## Install the CLI for use from other directories

From the repository checkout, run:

```bash
mise run install-cli
```

This installs the checkout as an editable tool for your user. You can then run `repotainer` from any directory while developing it. If the command is not found, run `uv tool update-shell` and reopen your terminal.
