from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console

app = typer.Typer()
console = Console()

MODULES: dict[str, dict[str, Any]] = {
    "config": {
        "config_section": {"config": {"extra_env_files": []}},
        "description": "Configuration module loading .env and TOML files",
    },
    "log": {
        "config_section": {"log": {"level": "info", "format": "dev"}},
        "description": "Unified structured logging module",
    },
    "retry": {
        "config_section": {"retry": {"max_attempts": 3, "backoff_factor": 2.0}},
        "description": "Resiliency module with retries and circuit breakers",
    },
    "ai": {
        "config_section": {"ai": {"default_provider": "openai", "default_model": "gpt-4o"}},
        "description": "AI provider module supporting OpenAI and Anthropic",
        "instructions": (
            "\nTo install AI dependencies:\n"
            "  pip install forge-runtime[openai] or forge-runtime[anthropic]\n"
            "  Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env"
        ),
    },
    "health": {
        "config_section": {"health": {"include_details": True, "check_timeout": 1.0}},
        "description": "Health checking for Kubernetes probes",
    },
    "cache": {
        "config_section": {"cache": {"backend": "memory", "default_ttl": 300}},
        "description": "Caching with in-memory and Redis backends",
        "instructions": (
            "✓ No additional dependencies required (in-memory backend)\n\n"
            "To use Redis backend:\n"
            "  pip install forge-runtime[redis]\n"
            "  Set REDIS_URL in .env"
        ),
    },
    "validation": {
        "config_section": {"validation": {}},
        "description": "Pydantic-integrated request/input validation",
    },
}


@app.command(name="add")
def add_command(
    module: str = typer.Argument(..., help="Module name to add (e.g., cache, ai)"),
    config_path: Path = typer.Option("forge.config.toml", "--config", "-c", help="Path to config file"),
) -> None:
    """
    Add a forge module to the project.

    Available modules: config, log, retry, ai, health, cache, validation
    """
    from forge.config.loaders import load_toml

    if module not in MODULES:
        console.print(f"[red]Error:[/red] Unknown module '{module}'.")
        console.print(f"Available modules: {', '.join(MODULES.keys())}")
        raise typer.Exit(code=1)

    if not config_path.exists():
        console.print(f"[red]Error:[/red] Configuration file '{config_path}' not found.")
        raise typer.Exit(code=1)

    try:
        config_data = load_toml(str(config_path))
    except Exception:
        config_data = {}

    module_info = MODULES[module]
    module_key = next(iter(module_info["config_section"].keys()))

    # If the key or wrapped forge.key is in config_data, warn and skip
    has_module = False
    if module_key in config_data or ("forge" in config_data and isinstance(config_data["forge"], dict) and module_key in config_data["forge"]):
        has_module = True

    if has_module:
        console.print(f"[yellow]Warning: Module '{module}' is already configured in '{config_path}'.[/yellow]")
        raise typer.Exit

    # Build the TOML snippet to append
    lines = [f"\n[{module_key}]"]
    config_sec = module_info["config_section"][module_key]
    for k, v in config_sec.items():
        if isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, bool):
            lines.append(f'{k} = {"true" if v else "false"}')
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}")
        elif isinstance(v, list):
            items_str = ", ".join(f'"{item}"' for item in v)
            lines.append(f"{k} = [{items_str}]")

    content = "\n".join(lines) + "\n"

    try:
        with open(config_path, "a", encoding="utf-8") as f:
            f.write(content)
    except Exception as err:
        console.print(f"[red]Error:[/red] Failed to write to '{config_path}': {err}")
        raise typer.Exit(code=1) from err

    console.print(f"[green]✓[/green] Added forge.{module} to {config_path}")

    # Print specific instructions
    if "instructions" in module_info:
        console.print(module_info["instructions"])
