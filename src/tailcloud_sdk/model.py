"""Command registration, validation, dispatch, and the TailCloud CLI protocol."""

import inspect
import json
import logging
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from contextlib import redirect_stdout
from dataclasses import replace
from typing import Any, TypeVar

from .errors import RegistrationError, ValidationError
from .models import Command, Field, Result
from .serialization import serialize

__all__ = ["Command", "Field", "Result", "TailModel", "serialize"]

logger = logging.getLogger(__name__)
Handler = TypeVar("Handler", bound=Callable[..., Result | None])
LIFECYCLE_ACTIONS = ("install", "update", "uninstall", "status")


class TailModel:
    """A local software integration executed by a TailCloud server agent.

    ``execute`` returns a Result for Python callers. ``init`` prints a single
    ``result=<JSON>`` response for the agent. Registration is synchronous.
    """

    def __init__(self, debug: bool = False):
        self.debug = debug
        self._commands: dict[str, Command] = {}
        self._lifecycle: dict[str, Command] = {}

    def command(self, command_data: Command) -> Callable[[Handler], Handler]:
        return self._register(self._commands, command_data)

    def install(self, command_data: Command) -> Callable[[Handler], Handler]:
        return self._register(self._lifecycle, command_data, "install")

    def update(self, command_data: Command) -> Callable[[Handler], Handler]:
        return self._register(self._lifecycle, command_data, "update")

    def uninstall(self, command_data: Command) -> Callable[[Handler], Handler]:
        return self._register(self._lifecycle, command_data, "uninstall")

    def status(self, command_data: Command) -> Callable[[Handler], Handler]:
        return self._register(self._lifecycle, command_data, "status")

    def _register(
        self, registry: dict[str, Command], definition: Command, key: str | None = None
    ) -> Callable[[Handler], Handler]:
        if not isinstance(definition, Command):
            raise TypeError("Command definition must be a Command instance")
        command_id = key or definition.id

        def decorator(func: Handler) -> Handler:
            if command_id in registry:
                raise RegistrationError(f"Command '{command_id}' is already registered")
            if (
                not callable(func)
                or inspect.iscoroutinefunction(func)
                or inspect.iscoroutinefunction(type(func).__call__)
            ):
                raise RegistrationError("Handlers must be synchronous callables")
            try:
                inspect.signature(func).bind(
                    **{item.id: item.default for item in definition.fields}
                )
            except (TypeError, ValueError) as exc:
                message = f"Handler signature does not match '{command_id}': {exc}"
                raise RegistrationError(message) from exc
            registry[command_id] = replace(definition, func=func)
            logger.debug("Registered command %s", command_id)
            return func

        return decorator

    def describe(self) -> dict[str, Any]:
        """Return metadata without running handlers or exposing callable objects."""
        return serialize({"commands": self._commands, **self._lifecycle})

    @staticmethod
    def _arguments(command: Command, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, Mapping) or any(not isinstance(key, str) for key in arguments):
            raise ValidationError("Arguments must be an object with string keys")
        known = {item.id for item in command.fields}
        if set(arguments) - known:
            raise ValidationError("Unknown command fields were provided")
        validated: dict[str, Any] = {}
        for item in command.fields:
            if item.id in arguments:
                validated[item.id] = item.validate(arguments[item.id])
            elif item.default is not None:
                validated[item.id] = item.default
            elif item.required:
                raise ValidationError(f"Field '{item.id}' is required")
        try:
            inspect.signature(command.func).bind(**validated)
        except TypeError as exc:
            message = "Missing arguments: declare field defaults or handler defaults"
            raise ValidationError(message) from exc
        return validated

    def execute(
        self,
        action: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        command_id: str | None = None,
    ) -> Result:
        """Execute a lifecycle action or ``command`` with an explicit command_id.

        Expected validation and handler failures become ERROR results.
        KeyboardInterrupt and SystemExit are intentionally not intercepted.
        """
        if action == "command":
            command = self._commands.get(command_id or "")
        elif action in LIFECYCLE_ACTIONS and command_id is None:
            command = self._lifecycle.get(action)
        else:
            command = None
        if command is None:
            return Result("Команда не найдена", status="ERROR")
        try:
            validated = self._arguments(command, {} if arguments is None else arguments)
        except ValidationError as exc:
            return Result("Некорректные параметры", description=str(exc), status="ERROR")
        try:
            assert command.func is not None
            result = command.func(**validated)
            if result is None:
                result = Result("Операция выполнена")
            if not isinstance(result, Result):
                raise TypeError("Handlers must return Result or None")
            serialize(result)
            return result
        except Exception:
            # Never log input values or exception text in normal operation.
            logger.error("Handler failed: %s", command.id, exc_info=self.debug)
            return Result(
                "Ошибка выполнения",
                description=(
                    traceback.format_exc()
                    if self.debug
                    else "Не удалось выполнить операцию"
                ),
                status="ERROR",
            )

    @staticmethod
    def _parse_arguments(raw: str) -> dict[str, Any]:
        try:
            arguments = json.loads(raw)
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise ValidationError("Arguments must be valid JSON") from exc
        if not isinstance(arguments, dict):
            raise ValidationError("Arguments must be a JSON object")
        return arguments

    def init(self, argv: Sequence[str] | None = None) -> dict[str, Any]:
        """Read CLI arguments, emit one protocol response, and return its payload.

        No arguments (or ``describe``) requests metadata. Handler stdout is
        redirected to stderr so ordinary print() calls do not break the protocol.
        """
        args = list(sys.argv[1:] if argv is None else argv)
        result = None
        try:
            if not args or args == ["describe"]:
                pass
            elif args[0] == "command" and len(args) in (2, 3):
                arguments = self._parse_arguments(args[2]) if len(args) == 3 else {}
                with redirect_stdout(sys.stderr):
                    result = self.execute("command", arguments, command_id=args[1])
            elif args[0] in LIFECYCLE_ACTIONS and len(args) in (1, 2):
                arguments = self._parse_arguments(args[1]) if len(args) == 2 else {}
                with redirect_stdout(sys.stderr):
                    result = self.execute(args[0], arguments)
            else:
                raise ValidationError(
                    "Usage: describe | command <id> [JSON] | "
                    "install/update/uninstall/status [JSON]"
                )
        except ValidationError as exc:
            result = Result("Некорректный запрос", description=str(exc), status="ERROR")
        payload = {**self.describe(), "result": serialize(result)}
        print("result=" + json.dumps(payload, ensure_ascii=False, allow_nan=False))
        return payload
