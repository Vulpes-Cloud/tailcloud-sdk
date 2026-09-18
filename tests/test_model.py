import contextlib
from enum import Enum
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import Mock

from tailcloud_sdk import Command, Field, RegistrationError, Result, TailModel, ValidationError
from tailcloud_sdk.serialization import serialize


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.model = TailModel()

    def cli(self, *args):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            payload = self.model.init(args)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("result="))
        self.assertEqual(json.loads(lines[0][7:]), payload)
        return payload, errors.getvalue()

    def test_command_dispatch_does_not_call_install(self):
        installer = Mock(return_value=Result("installed"))
        handler = Mock(return_value=Result("restarted"))
        self.model.install(Command("install", "Install"))(installer)
        self.model.command(Command("restart", "Restart"))(handler)
        payload, _ = self.cli("command", "restart")
        self.assertEqual(payload["result"]["title"], "restarted")
        handler.assert_called_once_with()
        installer.assert_not_called()

    def test_lifecycle_dispatch(self):
        for action in ("install", "update", "uninstall", "status"):
            with self.subTest(action=action):
                handler = Mock(return_value=Result(action))
                getattr(self.model, action)(Command(action, action))(handler)
                payload, _ = self.cli(action)
                self.assertEqual(payload["result"]["title"], action)
                handler.assert_called_once_with()

    def test_metadata_does_not_execute_handlers_or_serialize_functions(self):
        handler = Mock()
        self.model.install(Command("install", "Install"))(handler)
        for args in ((), ("describe",)):
            payload, _ = self.cli(*args)
            self.assertIsNone(payload["result"])
            self.assertNotIn("func", payload["install"])
        handler.assert_not_called()

    def test_malformed_requests_always_produce_an_error_response(self):
        for args in (
            ("command",), ("command", "missing"), ("unknown",),
            ("install",), ("describe", "extra"), ("install", "{}", "extra"),
            ("command", "test", "{"), ("install", "[]"), ("install", "null"),
            ("install", "1"), ("install", '"text"'),
        ):
            with self.subTest(args=args):
                payload, _ = self.cli(*args)
                self.assertEqual(payload["result"]["status"], "ERROR")

    def test_validation_prevents_execution_and_applies_defaults(self):
        handler = Mock(return_value=Result("done"))
        self.model.command(Command("test", "Test", fields=[
            Field("port", "Port", type="int", required=True, minimum=1, maximum=65535),
            Field("enabled", "Enabled", type="bool", default=False),
            Field("mode", "Mode", default="safe", choices=["safe", "fast"]),
        ]))(handler)
        for args in ({}, {"port": True}, {"port": "80"}, {"port": 0},
                     {"port": 65536}, {"port": 80, "unknown": 1},
                     {"port": 80, "enabled": "false"}, {"port": 80, "mode": "bad"},
                     {"port": None}, [], {1: "value"}):
            with self.subTest(args=args):
                result = self.model.execute("command", args, command_id="test")
                self.assertEqual(result.status, "ERROR")
        handler.assert_not_called()
        result = self.model.execute("command", {"port": 80}, command_id="test")
        self.assertEqual(result.status, "OK")
        handler.assert_called_once_with(port=80, enabled=False, mode="safe")

    def test_optional_fields_can_use_python_defaults(self):
        @self.model.command(Command("test", "Test", fields=[Field("name", "Name")]))
        def handler(name="world"):
            return Result(name)

        self.assertEqual(self.model.execute("command", command_id="test").title, "world")
        self.assertEqual(handler("direct").title, "direct")

    def test_prints_do_not_corrupt_protocol(self):
        @self.model.command(Command("test", "Test"))
        def handler():
            print("progress")
            return Result("Готово", data={"items": [1, 2]})

        payload, errors = self.cli("command", "test")
        self.assertEqual(errors, "progress\n")
        self.assertEqual(payload["result"]["data"], {"items": [1, 2]})

    def test_none_result_is_success(self):
        self.model.install(Command("install", "Install"))(lambda: None)
        payload, _ = self.cli("install")
        self.assertEqual(payload["result"]["status"], "OK")

    def test_handler_errors_do_not_expose_exception_details_by_default(self):
        def handler():
            raise RuntimeError("secret-token")

        self.model.install(Command("install", "Install"))(handler)
        with self.assertLogs("tailcloud_sdk", level="ERROR") as logs:
            payload, _ = self.cli("install")
        self.assertNotIn("secret-token", json.dumps(payload))
        self.assertNotIn("secret-token", " ".join(logs.output))
        self.model.debug = True
        with self.assertLogs("tailcloud_sdk", level="ERROR"):
            payload, _ = self.cli("install")
        self.assertIn("RuntimeError: secret-token", payload["result"]["description"])

    def test_invalid_return_values_are_reported(self):
        for value in (42, {}, Result("bad", data={"value": object()}),
                      Result("bad", data={"value": float("nan")})):
            with self.subTest(value=value):
                model = TailModel()
                model.install(Command("install", "Install"))(Mock(return_value=value))
                self.assertEqual(model.execute("install").status, "ERROR")

    def test_control_flow_exceptions_are_not_swallowed(self):
        for exception in (KeyboardInterrupt, SystemExit):
            model = TailModel()
            model.install(Command("install", "Install"))(Mock(side_effect=exception))
            with self.assertRaises(exception):
                model.execute("install")

    def test_duplicate_registration_is_rejected(self):
        definition = Command("test", "Test")
        self.model.command(definition)(lambda: None)
        with self.assertRaises(RegistrationError):
            self.model.command(definition)(lambda: None)
        self.assertIsNone(definition.func)

    def test_definition_can_be_reused_without_overwriting_handlers(self):
        definition = Command("test", "Test")
        other = TailModel()
        self.model.command(definition)(lambda: Result("first"))
        other.command(definition)(lambda: Result("second"))
        self.assertEqual(self.model.execute("command", command_id="test").title, "first")

    def test_invalid_handlers_fail_at_registration(self):
        async def asynchronous():
            pass

        for handler in (None, asynchronous, lambda missing: None):
            with self.subTest(handler=handler), self.assertRaises(RegistrationError):
                self.model.command(Command("test", "Test"))(handler)
        with self.assertRaises(RegistrationError):
            self.model.command(Command("test", "Test", fields=[Field("extra", "Extra")]))(lambda: None)

    def test_compatibility_import(self):
        from tailcloudSDK.model import TailModel as LegacyModel

        self.assertIs(LegacyModel, TailModel)


class MetadataTests(unittest.TestCase):
    def test_field_definition_validation(self):
        for kwargs in (
            {"id": "invalid-name"}, {"id": "class"}, {"type": "float"},
            {"type": "int", "default": True}, {"type": "int", "minimum": 10, "maximum": 1},
            {"minimum": 0}, {"type": "int", "minimum": False},
            {"choices": ["one"], "default": "two"}, {"required": True, "default": ""},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Field(**{"id": "value", "name": "Value", **kwargs})

    def test_required_string_rejects_whitespace(self):
        with self.assertRaises(ValidationError):
            Field("name", "Name", required=True).validate("  ")

    def test_duplicate_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            Command("test", "Test", fields=[Field("x", "X"), Field("x", "Other")])

    def test_serialization_is_explicit(self):
        class State(Enum):
            OK = "OK"

        self.assertEqual(serialize({"state": State.OK, "items": (1, 2)}),
                         {"state": "OK", "items": [1, 2]})
        for value in (object(), {1: "bad"}, {1, 2}, Result):
            with self.subTest(value=value), self.assertRaises(TypeError):
                serialize(value)

    def test_library_import_does_not_configure_root_logging(self):
        process = subprocess.run(
            [sys.executable, "-c", "import logging; before = logging.getLogger().handlers[:]; "
             "import tailcloud_sdk; assert logging.getLogger().handlers == before"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
