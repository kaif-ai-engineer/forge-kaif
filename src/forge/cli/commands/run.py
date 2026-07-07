from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command(name="run")
def run_command(
    app_path: str = typer.Argument("main:app", help="Path to ASGI application (module:app)"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
) -> None:
    """
    Run the development server.

    Uses uvicorn for ASGI applications.
    Runs config validation before starting.
    """
    from pathlib import Path

    from forge.cli.commands.check import check_config

    # Run check config first
    try:
        check_config(Path("forge.config.toml"), fix=False)
    except typer.Exit:
        raise

    try:
        import uvicorn
    except ImportError:
        console.print("[red]Error: uvicorn is not installed.[/red]")
        console.print("To run the development server, install uvicorn:")
        console.print("  [cyan]pip install uvicorn[/cyan]")
        console.print("Or install the full forge-kaif stack:")
        console.print("  [cyan]pip install forge-kaif[all][/cyan]")
        raise typer.Exit(code=1)

    console.print(f"Starting development server at http://{host}:{port}...")
    try:
        uvicorn.run(app_path, host=host, port=port, reload=reload)
    except Exception as err:
        console.print(f"[red]Error starting server:[/red] {err}")
        raise typer.Exit(code=1) from err
