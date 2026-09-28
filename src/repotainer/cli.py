import typer

from repotainer.commands.detect import app as detect_app

app = typer.Typer(no_args_is_help=True)
app.add_typer(detect_app)


@app.callback()
def root() -> None:
    """Repotainer command-line interface."""


def main() -> None:
    app()
