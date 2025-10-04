"""Utilities for discovering and loading VBot plugins."""
from __future__ import annotations

import importlib
import logging
import pkgutil
from types import ModuleType
import inspect
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set

logger = logging.getLogger(__name__)


class PluginLoader:
    """Discover and load plugin modules at runtime."""

    def __init__(
        self,
        package: str = "plugins",
        *,
        enabled_plugins: Optional[Sequence[str]] = None,
        disabled_plugins: Optional[Sequence[str]] = None,
    ) -> None:
        self.package_name = package
        self.enabled_plugins = (
            {self._normalize_name(name) for name in enabled_plugins}
            if enabled_plugins is not None
            else None
        )
        self.disabled_plugins: Set[str] = {
            self._normalize_name(name) for name in disabled_plugins or []
        }
        self.loaded_plugins: Dict[str, ModuleType] = {}
        self.failed_plugins: Dict[str, Exception] = {}
        self.handled_commands: Set[str] = set()
        self.command_handlers: Dict[str, Callable[[object, str, List[str]], object]] = {}

    @staticmethod
    def _normalize_name(name: str) -> str:
        return name.strip().lower()

    def _is_allowed(self, module_name: str) -> bool:
        short_name = module_name.rsplit(".", 1)[-1]
        normalized = self._normalize_name(short_name)
        if self.enabled_plugins is not None and normalized not in self.enabled_plugins:
            logger.debug("Skipping plugin %s because it is not enabled", module_name)
            return False
        if normalized in self.disabled_plugins:
            logger.debug("Skipping plugin %s because it is disabled", module_name)
            return False
        return True

    def discover_plugins(self) -> List[str]:
        """Return a list of fully qualified plugin module names."""
        try:
            package = importlib.import_module(self.package_name)
        except ModuleNotFoundError:
            logger.warning("Plugin package '%s' not found", self.package_name)
            return []

        package_path = getattr(package, "__path__", None)
        if not package_path:
            logger.warning(
                "Plugin package '%s' does not expose a __path__ attribute", self.package_name
            )
            return []

        discovered: List[str] = []
        prefix = f"{self.package_name}."
        for _, module_name, is_pkg in pkgutil.iter_modules(package_path, prefix):
            if is_pkg:
                continue
            if module_name.rsplit(".", 1)[-1].startswith("_"):
                continue
            discovered.append(module_name)
        return discovered

    async def load_plugins(self, bot: "VBot") -> List[str]:  # pragma: no cover - async IO wrapper
        """Import and initialize plugins, returning the loaded module names."""
        loaded: List[str] = []
        for module_name in self.discover_plugins():
            if not self._is_allowed(module_name):
                continue
            if module_name in self.loaded_plugins:
                logger.debug("Plugin %s already loaded", module_name)
                continue

            try:
                module = importlib.import_module(module_name)
                setup = getattr(module, "setup", None)
                if callable(setup):
                    result = setup(bot)
                    if inspect.isawaitable(result):
                        await result
                else:
                    logger.debug("Plugin %s does not define a callable setup", module_name)
                self._register_module_commands(module)
                self.loaded_plugins[module_name] = module
                loaded.append(module_name)
                logger.info("Plugin loaded: %s", module_name)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Failed to load plugin %s: %s", module_name, exc, exc_info=True)
                self.failed_plugins[module_name] = exc
        return loaded


    def _normalize_command(self, command: str) -> str:
        return command.strip().lower()

    def _register_module_commands(self, module: ModuleType) -> None:
        """Register the commands declared by a plugin module."""

        commands: Optional[Iterable[str]]
        commands = getattr(module, "HANDLED_COMMANDS", None)
        if commands is None:
            return

        if isinstance(commands, str):
            commands = [commands]

        try:
            for command in commands:
                if not isinstance(command, str):
                    logger.debug(
                        "Plugin %s provided a non-string command entry: %r",
                        module.__name__,
                        command,
                    )
                    continue
                normalized = self._normalize_command(command)
                if not normalized:
                    continue
                if normalized in self.handled_commands:
                    logger.warning(
                        "Command %s is already handled by another plugin; keeping first registration",
                        command,
                    )
                    continue
                self.handled_commands.add(normalized)
        except TypeError:
            logger.debug(
                "Plugin %s provided an invalid HANDLED_COMMANDS value", module.__name__
            )

    def handles_command(self, command: str) -> bool:
        """Return True if any plugin declares handling the given command."""

        if not command:
            return False
        return command.lower() in self.handled_commands

    def register_command_handler(
        self,
        commands: Iterable[str] | str,
        handler: Callable[[object, str, List[str]], object],
    ) -> bool:
        """Register an async or sync handler for one or more commands."""

        if isinstance(commands, str):
            commands = [commands]

        registered = False
        for command in commands:
            normalized = self._normalize_command(command)
            if not normalized:
                continue
            if normalized in self.command_handlers:
                logger.warning(
                    "Command %s already has a registered handler; keeping the first one",
                    command,
                )
                continue

            self.command_handlers[normalized] = handler  # type: ignore[assignment]
            self.handled_commands.add(normalized)
            registered = True

        return registered

    async def dispatch_command(
        self, command: str, message: object, parts: List[str]
    ) -> bool:
        """Invoke the registered handler for ``command`` if any."""

        if not command:
            return False

        handler = self.command_handlers.get(self._normalize_command(command))
        if handler is None:
            return False

        result = handler(message, command, parts)
        if inspect.isawaitable(result):
            await result
        return True


__all__ = ["PluginLoader"]
