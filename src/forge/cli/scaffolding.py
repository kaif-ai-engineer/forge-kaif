from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import jinja2


def render_template(content: str, variables: dict[str, Any]) -> str:
    """Render a template string using Jinja2."""
    template = jinja2.Template(content)
    return template.render(**variables)


def copy_template_dir(src: resources.abc.Traversable, dest: Path, variables: dict[str, Any]) -> None:
    """Recursively copy and render traversable templates."""
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        name_rendered = jinja2.Template(item.name).render(**variables)
        if name_rendered.endswith(".jinja"):
            name_rendered = name_rendered[:-6]
        elif name_rendered.endswith(".tmpl"):
            name_rendered = name_rendered[:-5]

        dest_item = dest / name_rendered

        if item.is_dir():
            copy_template_dir(item, dest_item, variables)
        else:
            content = item.read_text(encoding="utf-8")
            rendered_content = render_template(content, variables)
            dest_item.write_text(rendered_content, encoding="utf-8")


def create_project(target: Path, name: str, template: str) -> None:
    """Scaffold a new project in target directory from a template."""
    pkg_resources = resources.files("forge.cli")
    template_dir = pkg_resources / "templates" / template

    if not template_dir.is_dir():
        raise ValueError(f"Unknown template: {template!r}")

    variables = {
        "project_name": name,
        "PascalName": name.replace("-", "_").title().replace("_", ""),
        "module_name": name,
    }

    copy_template_dir(template_dir, target, variables)
