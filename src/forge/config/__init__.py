"""
Configuration module — layered config loading and Pydantic-based validation.

Loads configuration from environment variables, .env files, and TOML files
in a documented priority order. Validates types at startup and provides
typed access via pydantic-settings.
"""
