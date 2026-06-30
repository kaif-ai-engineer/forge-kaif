from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError
from rich.console import Console

app = typer.Typer()
console = Console()


def _unwrap_toml(raw: dict[str, Any]) -> dict[str, Any]:
    if "forge" in raw and isinstance(raw["forge"], dict):
        return raw["forge"]
    return raw


def check_config(config_path: Path, fix: bool) -> None:
    """Programmatic helper to validate forge configuration."""
    from forge.config.loaders import load_dotenv, load_toml
    from forge.config.schema import ForgeConfig

    if not config_path.exists():
        console.print(f"[red]Error: Configuration file '{config_path}' not found.[/red]")
        console.print(
            "Run `forge init` to scaffold a new project or create a configuration file manually."
        )
        raise typer.Exit(code=1)

    try:
        toml_raw = load_toml(str(config_path))
    except Exception as err:
        console.print(f"[red]Error: Failed to parse TOML from '{config_path}': {err}[/red]")
        raise typer.Exit(code=1) from err

    # Load env files
    if Path(".env").exists():
        for k, v in load_dotenv(".env").items():
            if k not in os.environ:
                os.environ[k] = v

    try:
        toml_data = _unwrap_toml(toml_raw)
        config = ForgeConfig(**toml_data)
    except ValidationError as e:
        console.print("[red]✗ Configuration validation failed:[/red]\n")
        for error in e.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            console.print(f"  [red]•[/red] {field}: {error['msg']}")
        raise typer.Exit(code=1)

    console.print("Checking configuration...")
    issues = []

    # 1. Environment
    console.print(f"  [green]✓[/green] environment: {config.environment}")

    # 2. AI default model
    default_model = config.ai.default_model
    console.print(f"  [green]✓[/green] forge.ai.default_model: {default_model}")

    # 3. OPENAI_API_KEY
    openai_key = (
        config.ai.openai_api_key.get_secret_value()
        if config.ai.openai_api_key
        else os.environ.get("OPENAI_API_KEY") or os.environ.get("FORGE_AI_OPENAI_API_KEY")
    )
    if openai_key:
        console.print("  [green]✓[/green] OPENAI_API_KEY: set (masked)")
    else:
        is_required = "gpt" in default_model
        if is_required:
            console.print("  [red]✗[/red] OPENAI_API_KEY: not set (required by forge.ai)")
            issues.append(
                {
                    "key": "OPENAI_API_KEY",
                    "reason": "required by forge.ai",
                    "fix": "export OPENAI_API_KEY=sk-your-key-here",
                }
            )
        else:
            console.print("  [green]✓[/green] OPENAI_API_KEY: not set (optional)")

    # 4. REDIS_URL
    if config.cache.backend == "redis":
        redis_url = config.cache.redis.url or os.environ.get("REDIS_URL")
        if redis_url:
            console.print("  [green]✓[/green] REDIS_URL: set")
        else:
            console.print(
                "  [red]✗[/red] REDIS_URL: not set (required by forge.cache when backend=redis)"
            )
            issues.append(
                {
                    "key": "REDIS_URL",
                    "reason": "required by forge.cache when backend=redis",
                    "fix": "export REDIS_URL=redis://localhost:6379/0",
                }
            )

    if issues:
        count = len(issues)
        issue_word = "issue" if count == 1 else "issues"
        if not fix:
            console.print(
                f"\n[red]✗ {count} {issue_word} found. Run `forge check config --fix` for remediation steps.[/red]"
            )
        else:
            console.print(f"\n[red]✗ {count} {issue_word} found.[/red]")
            console.print("\n[bold]Remediation Steps:[/bold]")
            for issue in issues:
                console.print(f"  • [bold]{issue['key']}[/bold] ({issue['reason']}):")
                console.print(f"      Run: [cyan]{issue['fix']}[/cyan]")
        raise typer.Exit(code=1)

    console.print("\n[green]✓ Configuration is valid.[/green]")


@app.command(name="config")
def check_command(
    config_path: Path = typer.Option(
        "forge.config.toml", "--config", "-c", help="Path to config file"
    ),
    fix: bool = typer.Option(False, "--fix", help="Attempt to fix issues"),
) -> None:
    """
    Validate the forge configuration.

    Checks:
    1. forge.config.toml exists and is valid TOML
    2. All required config keys are present
    3. All referenced env vars are set
    4. Module-specific validation
    """
    check_config(config_path, fix)
