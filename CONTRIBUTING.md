# Contributing to forge

We love contributions! Here's how to get started.

## Development Setup

1. Clone the repository:
   ```bash
    git clone https://github.com/kaif-ai-engineer/forge-kaif.git
   cd forge
   ```

2. Install uv (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. Create a virtual environment and install the package in development mode:
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -e ".[all]"
   ```

4. Verify the setup:
   ```bash
   python -c "import forge; print(forge.__version__)"
   ```

## Running Tests

```bash
# Run all tests
pytest

# Run only unit tests
pytest tests/unit

# Run only integration tests
pytest tests/integration

# Run with coverage
pytest --cov=forge
```

## Linting and Type Checking

```bash
# Format code
ruff format .

# Lint
ruff check .

# Type check
mypy src/forge
```

## Code Style

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) with a 100-character line limit
- Use `snake_case` for functions, variables, and file names
- Use `PascalCase` for classes
- Use `UPPER_SNAKE_CASE` for environment variables and constants
- All public APIs must have complete type annotations
- All public functions and classes must have docstrings
- No circular dependencies between modules
- `__init__.py` is the only public surface for each module

## Submitting a Pull Request

1. Create a new branch from `main`
2. Make your changes
3. Run linting and tests locally
4. Push your branch and open a pull request
5. Ensure CI passes on your PR

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation
- `refactor:` — code refactoring
- `test:` — test changes
- `chore:` — maintenance tasks

## Need Help?

Open a [Discussion](https://github.com/kaif-ai-engineer/forge-kaif/discussions) or
join our [Discord](https://discord.gg/forge).
