# Changelog

All notable changes to forge-kaif will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).



## 0.3.0 (2026-07-06)

### Added

- chore: update CHANGELOG.md for v0.2.0
- fix: suppress mypy attr-defined on google.generativeai.configure
- fix: resolve CI failures - mypy attr-defined error and gemini mock test
- fix: improve architecture, eliminate duplication, and harden production readiness
- Fix docs CI: install forge package for mkdocstrings
- Fix mypy/pytest CI: .gitignore hatch exclude, redis test skip, mypy ignore
- Fix mypy errors, add typer/email-validator deps
- Add pre-commit with ruff hooks, fix lint issues in tests
- Add fastapi dep, run ruff format on 30 files
- Fix CI: add dev deps, remove invalid mkdocs option
- Set up documentation website with MkDocs Material theme #19
- Implement CRUD Generation Module with template-based code generation (#18)
- Implement Ollama Local Model Adapter for complete() and stream() #17
- Implement full streaming support for Gemini adapter #16
- Implement Feature Flags module #15
- #14
- #13
- Implement Jobs Module with Scheduled Tasks and Background Job Queue
- feat: Implement forge CLI with Typer and Rich for beautiful output (#11)
- feat: Implement ValidationModule with Pydantic integration and @validate decorator (#10)
- feat: Implement CacheModule with pluggable in-memory LRU and Redis backends (#9)
- feat: implement health module for k8s probes (#8)
- Audit infrastructure and complete logging module #7
- feat: Implement AI Model Module Core with OpenAI and Anthropic Adapters (#6)
- feat: retry and resilience module with backoff strategies, circuit breaker, and RetryModule (#5)
- feat: structured logging module with JSON/dev formatters, non-blocking writes, and context propagation (#4)
- chore: add internal_docs to gitignore
- feat: config module with layered loading, pydantic-settings, and TOML support (#3)
- feat: core runtime & DI container (#2)
- feat: project foundation scaffolding (#1)
- add doc
- Initial commit
## 0.2.0 (2026-07-06)

### Added

- fix: suppress mypy attr-defined on google.generativeai.configure
- fix: resolve CI failures - mypy attr-defined error and gemini mock test
- fix: improve architecture, eliminate duplication, and harden production readiness
- Fix docs CI: install forge package for mkdocstrings
- Fix mypy/pytest CI: .gitignore hatch exclude, redis test skip, mypy ignore
- Fix mypy errors, add typer/email-validator deps
- Add pre-commit with ruff hooks, fix lint issues in tests
- Add fastapi dep, run ruff format on 30 files
- Fix CI: add dev deps, remove invalid mkdocs option
- Set up documentation website with MkDocs Material theme #19
- Implement CRUD Generation Module with template-based code generation (#18)
- Implement Ollama Local Model Adapter for complete() and stream() #17
- Implement full streaming support for Gemini adapter #16
- Implement Feature Flags module #15
- #14
- #13
- Implement Jobs Module with Scheduled Tasks and Background Job Queue
- feat: Implement forge CLI with Typer and Rich for beautiful output (#11)
- feat: Implement ValidationModule with Pydantic integration and @validate decorator (#10)
- feat: Implement CacheModule with pluggable in-memory LRU and Redis backends (#9)
- feat: implement health module for k8s probes (#8)
- Audit infrastructure and complete logging module #7
- feat: Implement AI Model Module Core with OpenAI and Anthropic Adapters (#6)
- feat: retry and resilience module with backoff strategies, circuit breaker, and RetryModule (#5)
- feat: structured logging module with JSON/dev formatters, non-blocking writes, and context propagation (#4)
- chore: add internal_docs to gitignore
- feat: config module with layered loading, pydantic-settings, and TOML support (#3)
- feat: core runtime & DI container (#2)
- feat: project foundation scaffolding (#1)
- add doc
- Initial commit
## 0.1.0 (unreleased)

### Added

- Project scaffolding and tooling configuration
- Module skeleton directories for all P0 modules
- CI/CD pipelines: test, lint, benchmark, publish
- Community files: README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, LICENSE
- Issue and PR templates
- AI agent discovery schema (forge.schema.json)
