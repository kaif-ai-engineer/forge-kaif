from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

from forge.cli.main import app

runner = CliRunner()


def test_cli_help() -> None:
    """Test displaying the CLI help menu."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.stdout


def test_cli_version() -> None:
    """Test displaying the version."""
    result = runner.invoke(app, ["-v"])
    assert result.exit_code == 0
    assert "forge-runtime" in result.stdout


def test_init_command_basic(tmp_path: Path) -> None:
    """Test scaffolding a basic project template."""
    project_name = "test-basic-project"
    result = runner.invoke(app, ["init", project_name, "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Project Initialized" in result.stdout

    proj_dir = tmp_path / project_name
    assert proj_dir.exists()
    assert (proj_dir / "forge.config.toml").exists()
    assert (proj_dir / "main.py").exists()
    assert (proj_dir / "pyproject.toml").exists()
    assert (proj_dir / ".env.example").exists()
    assert (proj_dir / ".gitignore").exists()
    assert (proj_dir / ".cursorrules").exists()


def test_init_command_fastapi(tmp_path: Path) -> None:
    """Test scaffolding a FastAPI project template."""
    project_name = "test-fastapi-project"
    result = runner.invoke(
        app,
        ["init", project_name, "--template", "fastapi", "--dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Project Initialized" in result.stdout

    proj_dir = tmp_path / project_name
    assert proj_dir.exists()
    pyproject_content = (proj_dir / "pyproject.toml").read_text()
    assert "fastapi" in pyproject_content


def test_init_command_overwrite_prompt(tmp_path: Path) -> None:
    """Test the init command overwrite prompts."""
    project_name = "test-overwrite-project"
    proj_dir = tmp_path / project_name
    proj_dir.mkdir()

    # Cancel overwrite
    result = runner.invoke(app, ["init", project_name, "--dir", str(tmp_path)], input="n\n")
    assert result.exit_code == 0
    assert "Cancelled project creation" in result.stdout

    # Confirm overwrite
    result = runner.invoke(app, ["init", project_name, "--dir", str(tmp_path)], input="y\n")
    assert result.exit_code == 0
    assert "Project Initialized" in result.stdout


def test_new_module_scaffolding(tmp_path: Path) -> None:
    """Test scaffolding a custom module."""
    module_name = "notifications"
    orig_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["new", "module", module_name])
        assert result.exit_code == 0
        assert "Created src/notifications/__init__.py" in result.stdout

        assert (tmp_path / "src" / "notifications" / "__init__.py").exists()
        assert (tmp_path / "src" / "notifications" / "module.py").exists()
        assert (tmp_path / "tests" / "test_notifications.py").exists()
    finally:
        os.chdir(orig_cwd)


def test_check_config(tmp_path: Path) -> None:
    """Test validating configuration checks."""
    orig_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)

        # Missing config file
        result = runner.invoke(app, ["check", "config"])
        assert result.exit_code == 1
        assert "Error: Configuration file" in result.stdout

        # Initialize project
        runner.invoke(app, ["init", "my-app", "--dir", str(tmp_path)])
        os.chdir(tmp_path / "my-app")

        # Missing OPENAI_API_KEY
        result = runner.invoke(app, ["check", "config"])
        assert result.exit_code == 1
        assert "OPENAI_API_KEY: not set" in result.stdout

        # Pass validation with env var set
        os.environ["OPENAI_API_KEY"] = "sk-test-key"
        try:
            result = runner.invoke(app, ["check", "config"])
            assert result.exit_code == 0
            assert "Configuration is valid" in result.stdout
        finally:
            del os.environ["OPENAI_API_KEY"]

        # Run with --fix
        result = runner.invoke(app, ["check", "config", "--fix"])
        assert result.exit_code == 1
        assert "Remediation Steps" in result.stdout
    finally:
        os.chdir(orig_cwd)


def test_add_module(tmp_path: Path) -> None:
    """Test adding modules to configuration."""
    orig_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        runner.invoke(app, ["init", "my-app", "--dir", str(tmp_path)])
        os.chdir(tmp_path / "my-app")

        # Add validation module
        result = runner.invoke(app, ["add", "validation"])
        assert result.exit_code == 0
        assert "Added forge.validation" in result.stdout

        # Re-adding should warn
        result = runner.invoke(app, ["add", "validation"])
        assert result.exit_code == 0
        assert "Warning: Module 'validation' is already configured" in result.stdout
    finally:
        os.chdir(orig_cwd)


def test_run_command_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test running the dev server command."""
    orig_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        runner.invoke(app, ["init", "my-app", "--dir", str(tmp_path)])
        os.chdir(tmp_path / "my-app")

        os.environ["OPENAI_API_KEY"] = "sk-test-key"

        from typing import Any

        mock_uvicorn = types.ModuleType("uvicorn")
        run_calls: list[tuple[str, dict[str, Any]]] = []

        def mock_run(app_path: str, **kwargs: Any) -> None:
            run_calls.append((app_path, kwargs))

        mock_uvicorn.run = mock_run  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "uvicorn", mock_uvicorn)

        result = runner.invoke(app, ["run", "main:app", "--port", "8500"])
        assert result.exit_code == 0
        assert "Starting development server" in result.stdout
        assert len(run_calls) == 1
        assert run_calls[0][0] == "main:app"
        assert run_calls[0][1]["port"] == 8500
    finally:
        os.chdir(orig_cwd)
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]
