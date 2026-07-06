from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer()
console = Console()


@app.command(name="init")
def init_command(
    project_name: str = typer.Argument(..., help="Name of the project to create"),
    template: str = typer.Option(
        "basic", "--template", "-t", help="Project template (basic, fastapi)"
    ),
    directory: Path = typer.Option(
        Path.cwd(), "--dir", "-d", help="Directory to create project in"
    ),
) -> None:
    """
    Scaffold a new forge project.

    Creates a project directory with default config, skeleton code,
    pyproject.toml, .env.example, .gitignore, and .cursorrules.
    """
    from forge.cli.scaffolding import create_project

    project_dir = directory / project_name

    if project_dir.exists():
        overwrite = typer.confirm(
            f"Directory '{project_dir}' already exists. Overwrite?",
            default=False,
        )
        if not overwrite:
            console.print("[yellow]Cancelled project creation.[/yellow]")
            raise typer.Exit

        shutil.rmtree(project_dir)

    with console.status(f"Creating [bold]{project_name}[/bold]..."):
        try:
            create_project(project_dir, project_name, template)
        except ValueError as err:
            console.print(f"[red]Error:[/red] {err}")
            raise typer.Exit(code=1) from err

    console.print(f"[green]✓[/green] Created {project_name}/")
    console.print("[green]✓[/green] Created forge.config.toml")
    console.print("[green]✓[/green] Created main.py")
    console.print("[green]✓[/green] Created pyproject.toml")
    console.print("[green]✓[/green] Created .env.example")
    console.print("[green]✓[/green] Created .gitignore")
    console.print("[green]✓[/green] Created .cursorrules")

    next_steps = (
        f"[dim]Next steps:[/dim]\n"
        f"  [cyan]cd {project_name}[/cyan]\n"
        f"  [cyan]pip install forge-kaif[/cyan]\n"
        f"  [cyan]cp .env.example .env[/cyan]  [dim]# Add your API keys[/dim]\n"
        f"  [cyan]python main.py[/cyan]"
    )
    console.print(
        Panel.fit(
            next_steps,
            title="[bold green]Project Initialized[/bold green]",
            border_style="green",
        )
    )
