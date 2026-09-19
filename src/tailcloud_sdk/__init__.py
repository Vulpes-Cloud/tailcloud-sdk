"""TailCloud SDK: declarative software integrations for server agents."""

import logging

from .errors import ExecutionError, RegistrationError, TailCloudError, ValidationError
from .model import TailModel
from .models import Command, Field, Result
from .runner import CommandResult, Runner
from .system import PackageManager, SystemdService

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "Command",
    "CommandResult",
    "ExecutionError",
    "Field",
    "PackageManager",
    "RegistrationError",
    "Result",
    "Runner",
    "SystemdService",
    "TailCloudError",
    "TailModel",
    "ValidationError",
]
