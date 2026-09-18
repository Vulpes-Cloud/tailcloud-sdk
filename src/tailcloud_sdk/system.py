"""Local Linux package and systemd helpers; no SSH connection is implied."""

import re
import shutil
from typing import Literal

from .errors import ExecutionError
from .runner import CommandResult, Runner

PackageBackend = Literal["apt-get", "dnf", "yum", "apk"]
_BACKENDS = ("apt-get", "dnf", "yum", "apk")


class PackageManager:
    """Install, upgrade, and remove named packages using the server's repositories.

    The caller supplies privileges. Repository indexes are refreshed only by an
    explicit refresh() call. No operation upgrades or removes unnamed packages.
    """

    def __init__(self, runner: Runner, backend: PackageBackend | None = None):
        if backend is None:
            backend = next((name for name in _BACKENDS if shutil.which(name)), None)
        if backend not in _BACKENDS:
            raise ValueError("A supported package manager is required: apt-get, dnf, yum, apk")
        self.runner = runner
        self.backend = backend

    def _run(self, operation: str, packages: tuple[str, ...] = ()) -> CommandResult:
        args = [self.backend]
        if self.backend != "apk":
            args.append("-y")
        args.extend([operation, *packages])
        env = {"DEBIAN_FRONTEND": "noninteractive"} if self.backend == "apt-get" else None
        return self.runner.run(args, env=env)

    @staticmethod
    def _validate_packages(packages: tuple[str, ...]) -> None:
        if not packages:
            raise ValueError("Specify at least one package")
        for package in packages:
            if not isinstance(package, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+._:-]*", package):
                raise ValueError("Package names must be literal names, not options, paths, or patterns")

    def refresh(self) -> CommandResult:
        operation = "makecache" if self.backend in ("dnf", "yum") else "update"
        return self._run(operation)

    def install(self, *packages: str) -> CommandResult:
        self._validate_packages(packages)
        return self._run("add" if self.backend == "apk" else "install", packages)

    def upgrade(self, *packages: str) -> CommandResult:
        self._validate_packages(packages)
        if self.backend == "apt-get":
            return self.runner.run(
                [self.backend, "-y", "install", "--only-upgrade", *packages],
                env={"DEBIAN_FRONTEND": "noninteractive"},
            )
        return self._run("upgrade", packages)

    def remove(self, *packages: str) -> CommandResult:
        self._validate_packages(packages)
        return self._run("del" if self.backend == "apk" else "remove", packages)


class SystemdService:
    """Control one explicitly named systemd unit."""

    def __init__(self, runner: Runner, name: str):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@:-]*", name):
            raise ValueError("Service name must be a literal systemd unit name")
        self.runner = runner
        self.name = name

    def _run(self, action: str, *options: str, check: bool = True) -> CommandResult:
        return self.runner.run(["systemctl", action, *options, "--", self.name], check=check)

    def start(self) -> CommandResult:
        return self._run("start")

    def stop(self) -> CommandResult:
        return self._run("stop")

    def restart(self) -> CommandResult:
        return self._run("restart")

    def reload(self) -> CommandResult:
        return self._run("reload")

    def enable(self, *, now: bool = False) -> CommandResult:
        return self._run("enable", *(('--now',) if now else ()))

    def disable(self, *, now: bool = False) -> CommandResult:
        return self._run("disable", *(('--now',) if now else ()))

    def status(self) -> CommandResult:
        return self._run("status", "--no-pager", "--full", check=False)

    def is_active(self) -> bool | None:
        """Return None during dry-run; infrastructure failures raise ExecutionError."""
        result = self._run("is-active", check=False)
        if result.skipped:
            return None
        if result.returncode == 0:
            return True
        if result.returncode in (3, 4):
            return False
        raise ExecutionError("Could not query systemd service state", result=result)
