from __future__ import annotations

from importlib import resources
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command(name="module")
def new_command(
    module_name: str = typer.Argument(..., help="Name of the custom module"),
    output_dir: Path = typer.Option(Path("src"), "--output-dir", "-o", help="Output directory for module"),
) -> None:
    """
    Generate a scaffold for a custom forge module.

    Creates:
    - src/{module_name}/__init__.py
    - src/{module_name}/module.py
    - tests/test_{module_name}.py
    """
    from forge.cli.scaffolding import render_template

    module_dir = output_dir / module_name
    module_dir.mkdir(parents=True, exist_ok=True)

    tests_dir = Path("tests")
    tests_dir.mkdir(parents=True, exist_ok=True)

    variables = {
        "module_name": module_name,
        "PascalName": module_name.replace("-", "_").title().replace("_", ""),
    }

    try:
        pkg_resources = resources.files("forge.cli")
        init_tmpl = (pkg_resources / "templates" / "module" / "__init__.py.jinja").read_text(encoding="utf-8")
        module_tmpl = (pkg_resources / "templates" / "module" / "module.py.jinja").read_text(encoding="utf-8")
        test_tmpl = (pkg_resources / "templates" / "module" / "test_module.py.jinja").read_text(encoding="utf-8")
    except Exception as err:
        console.print(f"[red]Error loading templates:[/red] {err}")
        raise typer.Exit(code=1) from err

    init_content = render_template(init_tmpl, variables)
    module_content = render_template(module_tmpl, variables)
    test_content = render_template(test_tmpl, variables)

    init_file = module_dir / "__init__.py"
    module_file = module_dir / "module.py"
    test_file = tests_dir / f"test_{module_name}.py"

    try:
        init_file.write_text(init_content, encoding="utf-8")
        module_file.write_text(module_content, encoding="utf-8")
        test_file.write_text(test_content, encoding="utf-8")
    except Exception as err:
        console.print(f"[red]Error writing scaffold files:[/red] {err}")
        raise typer.Exit(code=1) from err

    console.print(f"[green]✓[/green] Created {init_file}")
    console.print(f"[green]✓[/green] Created {module_file}")
    console.print(f"[green]✓[/green] Created {test_file}")
    console.print("\nEdit module.py to implement your ForgeModule.")
