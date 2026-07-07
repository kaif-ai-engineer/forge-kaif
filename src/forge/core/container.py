from __future__ import annotations

from collections import deque

from forge.core.exceptions import (
    CircularDependencyError,
    ModuleNotFoundError,
    ModuleRegistrationError,
)
from forge.core.module import ForgeModule, ModuleLifecycleState


class Container:
    """
    Lightweight explicit dependency injection container.

    This container holds all registered ``ForgeModule`` instances and
    provides type-safe retrieval.  Registration is explicit (not
    annotation-based) per `ADR-001`_.

    .. _ADR-001:
       https://github.com/kaif-ai-engineer/forge-kaif/blob/main/docs/ADR-001.md
    """

    def __init__(self) -> None:
        self._modules: dict[str, ForgeModule] = {}
        self._types: dict[type[ForgeModule], ForgeModule] = {}

    def register(self, module: ForgeModule, *, replace: bool = False) -> None:
        """
        Register a module instance.

        Parameters
        ----------
        module:
            An instantiated ``ForgeModule`` subclass.
        replace:
            If ``True``, silently replace an existing registration
            with the same name.  Otherwise raise
            ``ModuleRegistrationError`` on conflict.

        Raises
        ------
        ModuleRegistrationError
            When a module with the same name is already registered and
            ``replace`` is ``False``.
        """
        if module.name in self._modules and not replace:
            raise ModuleRegistrationError(
                f"A module named '{module.name}' is already registered. "
                f"Use ``replace=True`` to override."
            )
        self._modules[module.name] = module
        self._types[type(module)] = module
        module._transition(ModuleLifecycleState.REGISTERED)

    def get(self, module_type: type[ForgeModule]) -> ForgeModule:
        """
        Retrieve a registered module by its class.

        Parameters
        ----------
        module_type:
            The class of the registered module.

        Returns
        -------
        ForgeModule
            The registered module instance.

        Raises
        ------
        ModuleNotFoundError
            When no module of the requested type is registered.
        """
        module = self._types.get(module_type)
        if module is None:
            raise ModuleNotFoundError(f"No module of type '{module_type.__name__}' is registered.")
        return module

    def get_by_name(self, name: str) -> ForgeModule:
        """
        Retrieve a registered module by its name.

        Parameters
        ----------
        name:
            The unique module name.

        Returns
        -------
        ForgeModule
            The registered module instance.

        Raises
        ------
        ModuleNotFoundError
            When no module with the given name is registered.
        """
        module = self._modules.get(name)
        if module is None:
            raise ModuleNotFoundError(
                f"No module named '{name}' is registered. "
                f"Available: {', '.join(sorted(self._modules))}"
            )
        return module

    def has(self, module_type: type[ForgeModule]) -> bool:
        """Return ``True`` if a module of the given type is registered."""
        return module_type in self._types

    def has_name(self, name: str) -> bool:
        """Return ``True`` if a module with the given name is registered."""
        return name in self._modules

    @property
    def registered(self) -> list[ForgeModule]:
        """Return all registered module instances."""
        return list(self._modules.values())

    # ------------------------------------------------------------------
    # Topological sort
    # ------------------------------------------------------------------

    def _build_dependency_graph(self) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = {}
        for mod in self._modules.values():
            graph.setdefault(mod.name, set())
            for dep in mod.dependencies:
                if dep not in self._modules:
                    from forge.core.exceptions import ModuleNotFoundError

                    raise ModuleNotFoundError(
                        f"Module '{mod.name}' depends on '{dep}' but '{dep}' is not registered."
                    )
                graph[mod.name].add(dep)
        # Ensure every node is in the graph
        for name in self._modules:
            graph.setdefault(name, set())
        return graph

    def _detect_cycles(self, graph: dict[str, set[str]]) -> None:
        white, gray, black = 0, 1, 2
        color: dict[str, int] = dict.fromkeys(graph, white)
        parent: dict[str, str | None] = dict.fromkeys(graph)

        def dfs(node: str) -> None:
            color[node] = gray
            for neighbour in graph.get(node, set()):
                if color[neighbour] == gray:
                    cycle: list[str] = []
                    cur: str | None = node
                    while cur is not None:
                        cycle.append(cur)
                        if cur == neighbour:
                            break
                        cur = parent[cur]
                    cycle.reverse()
                    raise CircularDependencyError(
                        f"Circular dependency detected: {' -> '.join(cycle)} -> {neighbour}"
                    )
                if color[neighbour] == white:
                    parent[neighbour] = node
                    dfs(neighbour)
            color[node] = black

        for node in graph:
            if color[node] == white:
                dfs(node)

    def _topological_sort(self) -> list[ForgeModule]:
        graph = self._build_dependency_graph()
        self._detect_cycles(graph)

        in_degree: dict[str, int] = dict.fromkeys(graph, 0)
        for node, deps in graph.items():
            for _dep in deps:
                in_degree[node] = in_degree.get(node, 0) + 1

        queue: deque[str] = deque()
        for node, degree in in_degree.items():
            if degree == 0:
                queue.append(node)

        sorted_names: list[str] = []
        while queue:
            node = queue.popleft()
            sorted_names.append(node)
            for neighbour, deps in graph.items():
                if node in deps:
                    in_degree[neighbour] -= 1
                    if in_degree[neighbour] == 0:
                        queue.append(neighbour)

        if len(sorted_names) != len(graph):
            raise CircularDependencyError(
                "Could not resolve module initialisation order due to a circular dependency."
            )

        return [self._modules[name] for name in sorted_names]

    def initialization_order(self) -> list[ForgeModule]:
        """
        Return modules sorted by dependency order (topological sort).

        Modules with no dependencies appear first; modules that depend
        on others appear after their dependencies.
        """
        return self._topological_sort()
