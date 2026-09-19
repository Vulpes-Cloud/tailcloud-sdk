import os
import sys
import unittest
from unittest.mock import patch

from tailcloud_sdk import CommandResult, ExecutionError, PackageManager, Runner, SystemdService


class RunnerTests(unittest.TestCase):
    def test_real_process_and_literal_arguments(self):
        literal = "hello; echo not-a-command & $HOME"
        result = Runner().run([sys.executable, "-c", "import sys; print(sys.argv[1])", literal])
        self.assertTrue(result.ok)
        self.assertEqual(result.stdout.strip(), literal)

    def test_nonzero_exit_has_structured_output(self):
        args = [sys.executable, "-c", "import sys; print('problem', file=sys.stderr); sys.exit(7)"]
        with self.assertRaises(ExecutionError) as caught:
            Runner().run(args)
        self.assertEqual(caught.exception.result.returncode, 7)
        self.assertEqual(caught.exception.result.stderr.strip(), "problem")
        self.assertNotIn("problem", str(caught.exception))
        self.assertFalse(Runner().run(args, check=False).ok)

    def test_timeout(self):
        with self.assertRaisesRegex(ExecutionError, "timed out"):
            Runner(timeout=0.1).run([sys.executable, "-c", "import time; time.sleep(10)"])

    def test_missing_executable(self):
        with self.assertRaisesRegex(ExecutionError, "Could not start"):
            Runner().run(["tailcloud-executable-that-does-not-exist"])

    def test_dry_run_never_starts_a_process(self):
        with patch("tailcloud_sdk.runner.subprocess.run") as run:
            result = Runner(dry_run=True).run(["nonexistent", "argument"])
        run.assert_not_called()
        self.assertTrue(result.skipped)
        self.assertFalse(result.ok)
        self.assertIsNone(result.returncode)
        self.assertEqual(result.args, ("nonexistent", "argument"))

    def test_environment_overlay_preserves_parent(self):
        with patch.dict(os.environ, {"TAILCLOUD_PARENT": "preserved"}):
            result = Runner().run(
                [
                    sys.executable,
                    "-c",
                    "import os; print(os.environ['TAILCLOUD_PARENT'], "
                    "os.environ['TAILCLOUD_CHILD'])",
                ],
                env={"TAILCLOUD_CHILD": "added"},
            )
        self.assertEqual(result.stdout.strip(), "preserved added")
        self.assertNotIn("TAILCLOUD_CHILD", os.environ)

    def test_invalid_arguments_and_timeouts(self):
        for args in ("echo hi", [], [""], [123], ["echo", "\0"]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Runner(dry_run=True).run(args)
        for timeout in (0, -1, True, float("nan"), float("inf"), "30"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                Runner(timeout=timeout)
        with self.assertRaises(ValueError):
            Runner(dry_run=True).run(["echo"], timeout=0)


class PackageTests(unittest.TestCase):
    def test_package_operations_for_all_backends(self):
        for backend, refresh, install, upgrade, remove in (
            (
                "apt-get",
                ["-y", "update"],
                ["-y", "install", "nginx"],
                ["-y", "install", "--only-upgrade", "nginx"],
                ["-y", "remove", "nginx"],
            ),
            (
                "dnf",
                ["-y", "makecache"],
                ["-y", "install", "nginx"],
                ["-y", "upgrade", "nginx"],
                ["-y", "remove", "nginx"],
            ),
            (
                "yum",
                ["-y", "makecache"],
                ["-y", "install", "nginx"],
                ["-y", "upgrade", "nginx"],
                ["-y", "remove", "nginx"],
            ),
            ("apk", ["update"], ["add", "nginx"], ["upgrade", "nginx"], ["del", "nginx"]),
        ):
            with self.subTest(backend=backend):
                manager = PackageManager(Runner(dry_run=True), backend)
                self.assertEqual(manager.refresh().args, tuple([backend, *refresh]))
                self.assertEqual(manager.install("nginx").args, tuple([backend, *install]))
                self.assertEqual(manager.upgrade("nginx").args, tuple([backend, *upgrade]))
                self.assertEqual(manager.remove("nginx").args, tuple([backend, *remove]))

    def test_detect_backend(self):
        which = "tailcloud_sdk.system.shutil.which"
        with patch(which, side_effect=lambda name: "/bin/dnf" if name == "dnf" else None):
            self.assertEqual(PackageManager(Runner()).backend, "dnf")
        with patch(which, return_value=None):
            with self.assertRaises(ValueError):
                PackageManager(Runner())

    def test_apt_is_noninteractive(self):
        with patch.object(Runner, "run") as run:
            PackageManager(Runner(), "apt-get").install("nginx")
        self.assertEqual(run.call_args.kwargs["env"], {"DEBIAN_FRONTEND": "noninteractive"})

    def test_reject_ambiguous_or_empty_package_targets(self):
        manager = PackageManager(Runner(dry_run=True), "apt-get")
        for method in (manager.install, manager.upgrade, manager.remove):
            for packages in ((), ("--all",), ("nginx*",), ("a;reboot",), ("/tmp/file",), ("a b",)):
                with self.subTest(method=method, packages=packages), self.assertRaises(ValueError):
                    method(*packages)


class ServiceTests(unittest.TestCase):
    def test_service_commands(self):
        service = SystemdService(Runner(dry_run=True), "nginx.service")
        for action in ("start", "stop", "restart", "reload", "enable", "disable"):
            self.assertEqual(
                getattr(service, action)().args, ("systemctl", action, "--", "nginx.service")
            )
        self.assertEqual(
            service.enable(now=True).args, ("systemctl", "enable", "--now", "--", "nginx.service")
        )
        self.assertIn("--no-pager", service.status().args)
        self.assertIsNone(service.is_active())

    def test_is_active_distinguishes_service_state_from_system_failures(self):
        service = SystemdService(Runner(), "nginx")
        for code, expected in ((0, True), (3, False), (4, False)):
            with patch.object(Runner, "run", return_value=CommandResult((), code)):
                self.assertIs(service.is_active(), expected)
        with patch.object(Runner, "run", return_value=CommandResult((), 1)):
            with self.assertRaises(ExecutionError):
                service.is_active()

    def test_reject_service_patterns_and_options(self):
        for name in ("", "--all", "*.service", "nginx;reboot", "../nginx"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                SystemdService(Runner(), name)
