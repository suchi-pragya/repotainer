import typer

from repotainer.commands.main import run

app = typer.Typer()
app.command()(run)


def main() -> None:
    app()
