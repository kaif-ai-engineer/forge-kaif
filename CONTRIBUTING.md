# Contributing to forge

Thank you for your interest in contributing to forge! Everyone is welcome
to participate — whether you are fixing a bug, improving documentation, or
proposing a new feature.

This project is maintained by a single maintainer who has final authority
on roadmap, architecture, releases, and merge decisions. The guidelines
below exist to make collaboration productive and respectful for everyone.

## Before You Start

- **Start with a discussion.** For significant changes — new features,
  API design, architectural decisions — please open a
  [Discussion](https://github.com/kaif-ai-engineer/forge-kaif/discussions)
  first. This avoids wasted effort and ensures alignment with project
  direction.

- **Small fixes are welcome without discussion.** Bug fixes, typo
  corrections, and documentation improvements can be submitted directly
  as pull requests.

## How to Contribute

1. **Fork and branch.** Create a new branch from `main` for your work.

2. **Make your changes.** Follow the project's code style (see below).

3. **Run quality checks locally** before opening your PR:
   ```bash
   ruff format --check .
   ruff check .
   mypy src/forge
   pytest
   ```

4. **Open a pull request.** Every change must come through a pull request.
   Direct pushes to `main` are not permitted.

## Pull Request Review

- All pull requests are reviewed based on **quality, maintainability, and
  project direction**.
- **Submission does not guarantee acceptance.** The maintainer may request
  changes or decline a PR if it does not fit the project's goals.
- To increase the chance of acceptance:
  - Keep changes focused and minimal.
  - Include tests for new functionality.
  - Update documentation and the CHANGELOG.
  - Ensure CI passes.

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
   uv pip install -e ".[all,dev]"
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
