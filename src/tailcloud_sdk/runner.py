"""Small, synchronous subprocess runner with predictable failure behavior."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import os
from pathlib import Path
import subprocess

from .errors import ExecutionError


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    skipped: bool = False

    @property
    def ok(self) -> bool:
        """True only for an actual successful execution, never for a dry run."""
        return self.returncode == 0 and not self.skipped


class Runner:
    """Execute argument lists without a shell or automatic privilege escalation.

    A dry run returns the intended arguments without starting a process. Captured
    output is held in memory, so this runner is intended for finite commands.
    """

    def __init__(self, *, timeout: float = 300, dry_run: bool = False):
        self._validate_timeout(timeout)
        self.timeout = timeout
        self.dry_run = dry_run

    @staticmethod
    def _validate_timeout(timeout: float) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be a positive finite number")

    def run(
        self,
        args: Sequence[str],
        *,
        check: bool = True,
        timeout: float | None = None,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        if isinstance(args, (str, bytes)) or not isinstance(args, Sequence) or not args:
            raise ValueError("Pass a non-empty sequence of arguments, not a shell command")
        if any(not isinstance(arg, str) or "\0" in arg for arg in args) or not args[0]:
            raise ValueError("Arguments must be strings without null bytes")
        effective_timeout = self.timeout if timeout is None else timeout
        self._validate_timeout(effective_timeout)
        command = tuple(args)
        if self.dry_run:
            return CommandResult(command, returncode=None, skipped=True)
        try:
            completed = subprocess.run(
                command,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=effective_timeout,
                cwd=cwd,
                env=None if env is None else {**os.environ, **env},
            )
        except subprocess.TimeoutExpired as exc:
            raise ExecutionError(f"Process timed out after {effective_timeout:g} seconds") from exc
        except OSError as exc:
            raise ExecutionError("Could not start process") from exc
        result = CommandResult(command, completed.returncode, completed.stdout, completed.stderr)
        if check and not result.ok:
            # Output and arguments may contain secrets; expose them only via result.
            raise ExecutionError(f"Process exited with code {result.returncode}", result=result)
        return result
