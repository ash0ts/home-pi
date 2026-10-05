"""Installer regressions use disposable checkouts and fake external commands."""

import base64
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import configure
from lib import config
import setup as setup_module


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="home pi test ")
        self.root = Path(self.temporary.name) / "checkout with spaces"
        self.root.mkdir()
        shutil.copy2(REPO / "setup.sh", self.root / "setup.sh")
        shutil.copy2(REPO / "docker-compose.yaml", self.root / "docker-compose.yaml")
        shutil.copytree(REPO / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        self.fakebin = Path(self.temporary.name) / "bin"
        self.fakebin.mkdir()
        self.calls = Path(self.temporary.name) / "calls.jsonl"
        fake = self.fakebin / "docker"
        fake.write_text("#!/usr/bin/env python3\nimport json,os,sys\nwith open(os.environ['TEST_CALLS'], 'a') as f:\n f.write(json.dumps({'args':sys.argv[1:], 'env':{k:v for k,v in os.environ.items() if k in ('COMPOSE_FILE','COMPOSE_PROFILES','COMPOSE_PROJECT_NAME','PIHOLE_PASSWORD')}})+'\\n')\nprint(os.environ.get('TEST_OUTPUT',''))\nsys.exit(int(os.environ.get('TEST_EXIT','0')))\n")
        fake.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.fakebin) + os.pathsep + os.environ["PATH"],
                        TEST_CALLS=str(self.calls), PYTHONDONTWRITEBYTECODE="1")
        self.env.pop("PI_DOCKER_SUDO", None)
        self.addCleanup(self.temporary.cleanup)

    def run_setup(self, *args):
        return subprocess.run([str(self.root / "setup.sh"), *args], cwd=self.temporary.name,
                              capture_output=True, text=True, env=self.env)

    def configure(self):
        result = self.run_setup("configure", "--project-name", "retained-project")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_foreign_cwd_and_spaces_idempotence_secret_permissions(self):
        result = self.configure()
        path = self.root / ".env"
        data = path.read_bytes()
        values = config.load_env(path)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(base64.b64decode(values["SPEEDTEST_APP_KEY"][7:])), 32)
        self.assertNotIn(values["PIHOLE_PASSWORD"], result.stdout + result.stderr)
        self.assertNotIn(values["SPEEDTEST_APP_KEY"], result.stdout + result.stderr)
        again = self.run_setup("configure")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(path.read_bytes(), data)
        self.assertFalse(self.calls.exists())
        self.assertFalse((Path(self.temporary.name) / ".env").exists())

    def test_preserves_user_bytes_and_adds_only_missing(self):
        key = "base64:" + base64.b64encode(b"a" * 32).decode()
        original = f"# Owner comment\r\nSPEEDTEST_APP_KEY='{key}'\r\nCUSTOM='$(touch must-not-exist)'\r\n"
        (self.root / ".env").write_bytes(original.encode())
        self.configure()
        self.assertTrue((self.root / ".env").read_bytes().startswith(original.encode()))
        self.assertFalse((self.root / "must-not-exist").exists())

    def test_invalid_existing_key_never_rotated_or_disclosed(self):
        original = b"SPEEDTEST_APP_KEY=base64:invalid-synthetic-secret\n"
        (self.root / ".env").write_bytes(original)
        result = self.run_setup("configure", "--project-name", "retained-project")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / ".env").read_bytes(), original)
        self.assertIn("migration", result.stderr)
        self.assertNotIn("invalid-synthetic-secret", result.stderr + result.stdout)

    def test_all_dry_runs_create_no_files_and_make_no_calls(self):
        for command in ("configure", "validate", "start", "install-deps"):
            args = [command, "--dry-run"]
            if command == "configure":
                args += ["--project-name", "new-pi"]
            result = self.run_setup(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / ".env").exists())
        self.assertFalse((self.root / ".context").exists())
        self.assertFalse(list(self.root.rglob("__pycache__")))
        self.assertFalse(self.calls.exists())

    def test_project_identity_requires_explicit_name_and_refuses_change(self):
        result = self.run_setup("configure")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / ".env").exists())
        self.configure()
        previous = (self.root / ".env").read_bytes()
        result = self.run_setup("configure", "--project-name", "different-project")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / ".env").read_bytes(), previous)

    def test_root_rejected_before_writes(self):
        with patch.object(configure, "ROOT", self.root), patch.object(config, "ROOT", self.root), patch.object(os, "geteuid", return_value=0):
            with self.assertRaisesRegex(config.ConfigError, "not root"):
                configure.configure("new-pi")
        self.assertFalse((self.root / ".env").exists())
        self.assertFalse((self.root / ".context").exists())

    def test_concurrent_configure_fails_without_config_write(self):
        directory = self.root / ".context"
        directory.mkdir()
        with (directory / "setup.lock").open("w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_setup("configure", "--project-name", "new-pi")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another", result.stderr)
        self.assertFalse((self.root / ".env").exists())

    def test_docker_argv_project_and_environment_are_preserved(self):
        self.configure()
        hostile = {**self.env, "COMPOSE_FILE": "/tmp/unrelated.yaml", "COMPOSE_PROFILES": "all",
                   "COMPOSE_PROJECT_NAME": "wrong", "PIHOLE_PASSWORD": "shell-secret"}
        with patch.object(config, "ROOT", self.root), patch.dict(os.environ, hostile):
            with self.assertRaises(config.ConfigError):
                config.run_compose("ps")
        self.assertFalse(self.calls.exists())
        hostile.pop("COMPOSE_FILE")
        hostile.pop("COMPOSE_PROFILES")
        with patch.object(config, "ROOT", self.root), patch.dict(os.environ, hostile), patch("lib.selection.selected", return_value=["health"]):
            config.run_compose("ps", "--format", "table {{.Names}}\t{{.Status}}")
        call = json.loads(self.calls.read_text())
        expected = ["compose", "--project-directory", str(self.root), "--env-file", str(self.root / ".env"),
                    "--project-name", "retained-project", "--profile", "health", "-f", str(self.root / "docker-compose.yaml"),
                    "ps", "--format", "table {{.Names}}\t{{.Status}}"]
        self.assertEqual(call["args"], expected)
        self.assertEqual(call["env"], {})

    def test_sudo_runner_keeps_arguments(self):
        self.configure()
        sudo = self.fakebin / "sudo"
        sudo.write_text('#!/bin/sh\n[ "$1" = "-n" ] || exit 9\nshift\nexec "$@"\n')
        sudo.chmod(0o755)
        with patch.object(config, "ROOT", self.root), patch.dict(os.environ, {**self.env, "PI_DOCKER_SUDO": "1"}):
            config.docker("ps", "--format", "table {{.Names}}\t{{.Status}}")
        self.assertEqual(json.loads(self.calls.read_text())["args"][-1], "table {{.Names}}\t{{.Status}}")

    def test_docker_failure_and_timeout_suppress_output(self):
        with patch.object(config, "ROOT", self.root), patch.dict(os.environ, {**self.env, "TEST_EXIT": "1", "TEST_OUTPUT": "SYNTHETIC-SECRET"}):
            with self.assertRaises(config.ConfigError) as result:
                config.docker("info")
        self.assertNotIn("SYNTHETIC-SECRET", str(result.exception))
        with patch.object(config, "ROOT", self.root), patch.object(config.subprocess, "run", side_effect=subprocess.TimeoutExpired("docker", 1, output="SYNTHETIC-SECRET")):
            with self.assertRaisesRegex(config.ConfigError, "timed out"):
                config.docker("info", timeout=1)

    def test_interpolation_is_rejected_without_echo(self):
        (self.root / ".env").write_text("SPEEDTEST_APP_KEY=$VERY_SECRET_VALUE\n")
        result = self.run_setup("configure", "--project-name", "new-pi")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("VERY_SECRET_VALUE", result.stdout + result.stderr)
        self.assertIn("single quote", result.stderr)

    def test_missing_env_helpful_failure_without_docker(self):
        with patch.object(config, "ROOT", self.root):
            with self.assertRaisesRegex(config.ConfigError, "Missing .env"):
                config.run_compose("up", "-d")
        self.assertFalse(self.calls.exists())

    def test_symlink_env_rejected(self):
        destination = Path(self.temporary.name) / "other-private-file"
        destination.write_text("sensitive existing file\n")
        (self.root / ".env").symlink_to(destination)
        result = self.run_setup("configure", "--project-name", "new-pi")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(destination.read_text(), "sensitive existing file\n")

    def test_bad_command_never_invokes_external_commands(self):
        result = self.run_setup("unknown")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_missing_dependency_stops_before_docker_or_start(self):
        with patch.object(setup_module, "platform_check"), patch.object(setup_module.shutil, "which", return_value=None), patch.object(setup_module, "docker") as runner:
            with self.assertRaisesRegex(config.ConfigError, "Missing dependency"):
                setup_module.preflight()
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
