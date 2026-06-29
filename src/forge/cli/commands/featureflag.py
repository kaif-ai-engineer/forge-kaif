from __future__ import annotations

import json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from forge.featureflags._state import get_featureflags_module
from forge.featureflags.exceptions import FlagNotFoundError
from forge.featureflags.models import (
    EvaluationContext,
    FlagDefinition,
    FlagType,
)

app = typer.Typer(help="Manage feature flags.")
console = Console()


def _require_module() -> Any:
    """Get the active FeatureFlagsModule or exit."""
    mod = get_featureflags_module()
    if mod is None:
        console.print("[red]Error:[/red] FeatureFlagsModule is not initialized. Start the runtime first.")
        raise typer.Exit(code=1)
    return mod


@app.command(name="list")
def list_flags(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all registered feature flags."""
    import asyncio

    mod = _require_module()
    flags = asyncio.run(mod.list_flags())

    if json_output:
        data = [f.model_dump(mode="json") for f in flags]
        console.print(json.dumps(data, indent=2))
        return

    if not flags:
        console.print("[yellow]No feature flags registered.[/yellow]")
        return

    table = Table(title="Feature Flags")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Default", style="green")
    table.add_column("Description")
    table.add_column("Rules", justify="right")

    for flag in flags:
        rules_count = len(flag.rules)
        overrides_count = len(flag.overrides)
        extra = f"{rules_count}r/{overrides_count}o" if rules_count or overrides_count else ""
        table.add_row(
            flag.name,
            flag.type.value,
            str(flag.default_value),
            flag.description or "",
            extra,
        )

    console.print(table)


@app.command(name="get")
def get_flag(
    name: str = typer.Argument(..., help="Flag name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Get details of a specific feature flag."""
    import asyncio

    mod = _require_module()
    try:
        flag = asyncio.run(mod.get_flag(name))
    except FlagNotFoundError:
        console.print(f"[red]Error:[/red] Flag '{name}' not found.")
        raise typer.Exit(code=1)

    if flag is None:
        console.print(f"[red]Error:[/red] Flag '{name}' not found.")
        raise typer.Exit(code=1)

    if json_output:
        console.print(json.dumps(flag.model_dump(mode="json"), indent=2))
        return

    console.print(f"[bold cyan]Name:[/bold cyan] {flag.name}")
    console.print(f"[bold cyan]Type:[/bold cyan] {flag.type.value}")
    console.print(f"[bold cyan]Default:[/bold cyan] {flag.default_value}")
    console.print(f"[bold cyan]Description:[/bold cyan] {flag.description or '(none)'}")

    if flag.overrides:
        console.print("\n[bold]Overrides:[/bold]")
        for key, val in flag.overrides.items():
            console.print(f"  {key}: {val}")

    if flag.rules:
        console.print("\n[bold]Rules:[/bold]")
        for i, rule in enumerate(flag.rules):
            console.print(f"  [{i}] value={rule.value}", highlight=False)
            if rule.percentage is not None:
                console.print(f"      percentage={rule.percentage}%")
            if rule.segments:
                for seg in rule.segments:
                    console.print(f"      segment: {seg.attribute} {seg.operator} {seg.values}")


@app.command(name="set")
def set_flag(
    name: str = typer.Argument(..., help="Flag name"),
    default_value: str = typer.Option("false", "--default", "-d", help="Default value (JSON-encoded)"),
    flag_type: str = typer.Option("boolean", "--type", "-t", help="Flag type: boolean, percentage, segment"),
    description: str = typer.Option("", "--description", "-desc", help="Flag description"),
) -> None:
    """Create or update a feature flag."""
    import asyncio

    mod = _require_module()

    try:
        ftype = FlagType(flag_type)
    except ValueError:
        console.print(f"[red]Error:[/red] Invalid flag type '{flag_type}'. Choose from: boolean, percentage, segment.")
        raise typer.Exit(code=1)

    try:
        parsed_default = json.loads(default_value)
    except json.JSONDecodeError:
        parsed_default = default_value

    flag = FlagDefinition(
        name=name,
        type=ftype,
        default_value=parsed_default,
        description=description,
    )

    asyncio.run(mod.set_flag(flag))
    console.print(f"[green]✓[/green] Flag '{name}' saved.")


@app.command(name="delete")
def delete_flag(
    name: str = typer.Argument(..., help="Flag name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a feature flag."""
    import asyncio

    mod = _require_module()

    if not force:
        typer.confirm(f"Delete flag '{name}'?", abort=True)

    deleted = asyncio.run(mod.delete_flag(name))
    if deleted:
        console.print(f"[green]✓[/green] Flag '{name}' deleted.")
    else:
        console.print(f"[yellow]Flag '{name}' not found.[/yellow]")


@app.command(name="evaluate")
def evaluate_flag(
    name: str = typer.Argument(..., help="Flag name"),
    user_id: str = typer.Option("", "--user-id", "-u", help="User ID for evaluation context"),
    region: str = typer.Option("", "--region", "-r", help="Region for evaluation context"),
    properties: str | None = typer.Option(None, "--properties", "-p", help="JSON-encoded properties dict"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Evaluate a feature flag for a given context."""
    import asyncio

    mod = _require_module()

    parsed_props: dict[str, Any] = {}
    if properties:
        try:
            parsed_props = json.loads(properties)
            if not isinstance(parsed_props, dict):
                console.print("[red]Error:[/red] --properties must be a JSON object.")
                raise typer.Exit(code=1)
        except json.JSONDecodeError as exc:
            console.print(f"[red]Error:[/red] Invalid JSON for --properties: {exc}")
            raise typer.Exit(code=1)

    context = EvaluationContext(
        user_id=user_id or "anonymous",
        region=region,
        properties=parsed_props,
    )

    try:
        result = asyncio.run(mod.evaluate(name, context))
    except FlagNotFoundError:
        console.print(f"[red]Error:[/red] Flag '{name}' not found.")
        raise typer.Exit(code=1)

    if json_output:
        console.print(json.dumps(result.model_dump(mode="json"), indent=2))
        return

    console.print(f"[bold cyan]Flag:[/bold cyan] {result.flag_name}")
    console.print(f"[bold cyan]Value:[/bold cyan] {result.value}")
    console.print(f"[bold cyan]Reason:[/bold cyan] {result.reason.value}")
    if result.matched_rule_index is not None:
        console.print(f"[bold cyan]Matched Rule:[/bold cyan] #{result.matched_rule_index}")


@app.command(name="add-rule")
def add_rule(
    name: str = typer.Argument(..., help="Flag name"),
    value: str = typer.Option("true", "--value", "-v", help="Rule value (JSON-encoded)"),
    percentage: int | None = typer.Option(None, "--percentage", "-pct", help="Rollout percentage (0-100)"),
    segment_attribute: str | None = typer.Option(None, "--segment-attr", "-sa", help="Segment attribute (user_id, region, or properties.KEY)"),
    segment_operator: str = typer.Option("eq", "--segment-op", "-so", help="Segment operator"),
    segment_values: str | None = typer.Option(None, "--segment-values", "-sv", help="Segment values (comma-separated)"),
) -> None:
    """Add an evaluation rule to an existing flag."""
    import asyncio

    mod = _require_module()

    flag = asyncio.run(mod.get_flag(name))
    if flag is None:
        console.print(f"[red]Error:[/red] Flag '{name}' not found.")
        raise typer.Exit(code=1)

    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    rule_data: dict[str, Any] = {"value": parsed_value}

    if percentage is not None:
        rule_data["percentage"] = percentage

    if segment_attribute and segment_values:
        rule_data["segments"] = [
            {
                "attribute": segment_attribute,
                "operator": segment_operator,
                "values": [v.strip() for v in segment_values.split(",") if v.strip()],
            }
        ]

    from forge.featureflags.models import FlagRule

    rule = FlagRule.model_validate(rule_data)
    flag.rules.append(rule)
    asyncio.run(mod.set_flag(flag))
    console.print(f"[green]✓[/green] Rule added to flag '{name}'.")
