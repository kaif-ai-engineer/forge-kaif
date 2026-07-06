# Writing a Custom Module

forge is designed to be extended. You can write custom modules that integrate with
the runtime, get dependency injection, health checks, and lifecycle management.

## Module Interface

Every module implements the `ForgeModule` interface:

```python
from forge import ForgeModule
from forge.health import HealthResult


class MyModule(ForgeModule):
    @property
    def name(self) -> str:
        return "my_module"

    @property
    def dependencies(self) -> list[str]:
        return ["config", "log"]

    async def setup(self, runtime) -> None:
        # Access other modules via DI
        config = runtime.get("config")
        self.log = runtime.get("log").get(self.name)
        self.api_key = config["MY_API_KEY"]
        await self.initialize_client()

    async def teardown(self) -> None:
        await self.close_client()

    async def health_check(self) -> HealthResult:
        if self.client_is_healthy():
            return HealthResult.ok()
        return HealthResult.error("Client connection lost")
```

## Runtime Registration

```python
from forge import ForgeRuntime

runtime = ForgeRuntime()
runtime.register(ConfigModule())
runtime.register(LogModule())
runtime.register(MyModule())  # Dependencies resolved automatically

await runtime.init()
```

## Publishing as a Plugin

Package your module as a standalone package:

```python
# pyproject.toml
[project]
name = "forge-my-module"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["forge-kaif"]

[project.entry-points."forge.plugins"]
my_module = "forge_my_module:MyModule"
```

Users can then install and configure your plugin:

```toml
# forge.config.toml
plugins = ["forge-my-module"]
```
