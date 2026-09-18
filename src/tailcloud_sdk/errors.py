"""Exceptions that callers may handle without parsing display messages."""


class TailCloudError(Exception):
    """Base exception for SDK errors."""


class ValidationError(TailCloudError, ValueError):
    """Command arguments do not match the declared fields."""


class RegistrationError(TailCloudError, ValueError):
    """A command definition or handler cannot be registered."""


class ExecutionError(TailCloudError):
    """An external process failed to start, timed out, or exited unsuccessfully."""

    def __init__(self, message: str, *, result=None):
        super().__init__(message)
        self.result = result
