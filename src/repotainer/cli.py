import typer

app = typer.Typer(no_args_is_help=True)


@app.callback()
def root() -> None:
    """Repotainer command-line interface."""


@app.command()
def hello() -> None:
    typer.echo("Hello from Repotainer!")


def main() -> None:
    app()
