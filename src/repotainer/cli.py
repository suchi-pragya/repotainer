import typer

from repotainer.commands.detect import detect

app = typer.Typer()
app.command()(detect)


def main() -> None:
    app()
