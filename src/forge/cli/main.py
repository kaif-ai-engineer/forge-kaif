from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="forge",
    help="forge-runtime: Python developer infrastructure framework",
)
console = Console()

# Import command handlers
from forge.cli.commands import add, check, init, new, run

# Add commands directly to main app
app.command(name="init")(init.init_command)
app.command(name="add")(add.add_command)
app.command(name="run")(run.run_command)

# Add sub-apps for nested subcommands: check, new
app.add_typer(check.app, name="check", help="Validate configuration.")
app.add_typer(new.app, name="new", help="Scaffold new custom module.")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit.", is_eager=True),
) -> None:
    if version:
        from forge._version import __version__
        console.print(f"forge-runtime [bold green]{__version__}[/bold green]")
        raise typer.Exit
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit


def main() -> None:
    app()


if __name__ == "__main__":
    main()
