import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import doctor


def completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class DoctorTests(unittest.TestCase):
    def test_disabled_services_and_explicit_scope(self):
        model = {"services": {"pihole": {}, "webtop": {"profiles": ["browser"]}}}
        self.assertEqual(doctor.selected_services(model, {}), ["pihole"])
        self.assertEqual(doctor.selected_services(model, {"COMPOSE_PROFILES": "browser"}), ["pihole", "webtop"])
        with self.assertRaises(doctor.ConfigError):
            doctor.selected_services(model, {}, ["webtop"])

    def test_stopped_required_service_fails(self):
        with patch.object(doctor, "run_compose", return_value=completed("a" * 64)), patch.object(doctor, "docker", return_value=completed('["exited", "none", []]')):
            result, _, _ = doctor.container_observation("pihole")
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(doctor.successful([result]))

    def test_missing_container_and_probe_errors_are_redacted(self):
        secret = "synthetic-never-print-this-token"
        with patch.object(doctor, "run_compose", return_value=completed(secret, 1, secret)):
            result, identifier, _ = doctor.container_observation("pihole")
        self.assertEqual(result["status"], "FAIL")
        self.assertIsNone(identifier)
        self.assertNotIn(secret, json.dumps(result))

    def test_inspect_selects_no_environment_or_health_logs(self):
        with patch.object(doctor, "run_compose", return_value=completed("b" * 64)), patch.object(doctor, "docker", return_value=completed('["running", "healthy", []]')) as call:
            result, _, _ = doctor.container_observation("pihole")
        self.assertEqual(result["status"], "PASS")
        self.assertNotIn(".Config.Env", str(call.call_args))
        self.assertNotIn(".State.Health.Log", str(call.call_args))

    def test_http_401_proves_liveness_only(self):
        connection = Mock()
        connection.getresponse.return_value.status = 401
        with patch.object(doctor.http.client, "HTTPSConnection", return_value=connection):
            result = doctor.http_observation("webtop", (3002, "https", "/"))
        self.assertEqual(result["status"], "PASS")
        self.assertIn("login has not been tested", result["evidence"])
        connection.close.assert_called_once()

    def test_http_failure_and_tls_failure_fail(self):
        for failure in (ssl.SSLError("secret-value"), ConnectionRefusedError("secret-value")):
            with self.subTest(failure=type(failure)), patch.object(doctor.http.client, "HTTPSConnection", side_effect=failure):
                result = doctor.http_observation("webtop", (3002, "https", "/"))
            self.assertEqual(result["status"], "FAIL")
            self.assertNotIn("secret-value", json.dumps(result))

    def test_http_endpoint_follows_namespace_owner(self):
        model = {"services": {"webtop": {"network_mode": "service:gluetun"}, "gluetun": {"ports": [{"target": 3001, "published": "3002", "host_ip": "127.0.0.1"}]}}}
        self.assertEqual(doctor.http_endpoint("webtop", model), (3002, "https", "/"))

    def test_pihole_non_json_upstreams_compared_without_printing_values(self):
        spec = {"environment": {"FTLCONF_dns_upstreams": "1.1.1.1;9.9.9.9"}}
        with patch.object(doctor, "docker", return_value=completed("[ 1.1.1.1, 9.9.9.9 ]\n")):
            result = doctor.upstream_observation("a" * 64, spec)
        self.assertEqual(result["status"], "PASS")
        self.assertNotIn("1.1.1.1", json.dumps(result))
        with patch.object(doctor, "docker", return_value=completed("[ 8.8.8.8 ]\n")):
            self.assertEqual(doctor.upstream_observation("a" * 64, spec)["status"], "FAIL")

    def test_tailscale_enrollment_not_crash_or_node_dump(self):
        private = json.dumps({"BackendState": "NeedsLogin", "Peer": {"private-device": "secret"}})
        with patch.object(doctor, "docker", return_value=completed(private, 1)):
            result = doctor.tailscale_observation("a" * 64)
        self.assertEqual(result["status"], "NEEDS_CONFIGURATION")
        self.assertNotIn("private-device", json.dumps(result))
        self.assertNotIn("secret", json.dumps(result))

    def test_dns_empty_success_is_not_healthy(self):
        with patch.object(doctor, "dns_query", return_value=("NOERROR", [])):
            checks = doctor.dns_observations({"DNS_PROBE_SERVER": "127.0.0.1"})
        self.assertEqual([c["status"] for c in checks], ["FAIL", "FAIL", "NEEDS_CONFIGURATION"])

    def test_dns_fixture_and_missing_binary(self):
        env = {"DNS_PROBE_SERVER": "127.0.0.1", "DNS_BLOCK_TEST_NAME": "blocked.example", "DNS_BLOCK_TEST_ADDRESS": "0.0.0.0"}
        with patch.object(doctor, "dns_query", side_effect=[("NOERROR", ["1.1.1.1"])] * 2 + [("NOERROR", ["0.0.0.0"])] * 2):
            checks = doctor.dns_observations(env)
        self.assertTrue(all(c["status"] == "PASS" for c in checks))
        with patch.object(doctor.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(doctor.dns_query("127.0.0.1", "example.com"), ("missing", []))

    def test_dns_requires_declared_target(self):
        self.assertEqual(doctor.dns_observations({})[0]["status"], "NEEDS_CONFIGURATION")

    def test_home_missing_and_invalid_evidence_never_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            self.assertTrue(all(c["status"] == "NEEDS_CONFIGURATION" for c in doctor.home_checks(path)))
            path.write_text(json.dumps({"schema_version": 1, "checks": [{"id": "secret-unknown-control"}]}))
            path.chmod(0o600)
            result = doctor.home_checks(path)
            self.assertTrue(all(c["status"] == "NEEDS_CONFIGURATION" for c in result))
            self.assertNotIn("secret-unknown-control", json.dumps(result))

    def test_fresh_manual_evidence_only_and_no_free_text_echo(self):
        now = datetime(2026, 10, 5, tzinfo=timezone.utc)
        row = {"id": "router_support", "scope": "owner", "status": "PASS", "method": "manual", "observed_at": doctor.stamp(now), "evidence_supplied": True, "evidence": "secret-never-echo"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps({"schema_version": 1, "checks": [row]}))
            path.chmod(0o600)
            result = doctor.home_checks(path, now)
            self.assertEqual(result[0]["status"], "PASS")
            self.assertNotIn("secret-never-echo", json.dumps(result))
            self.assertEqual(doctor.home_checks(path, now + timedelta(days=31))[0]["status"], "NEEDS_CONFIGURATION")
            row["method"] = "automatic"
            path.write_text(json.dumps({"schema_version": 1, "checks": [row]}))
            self.assertEqual(doctor.home_checks(path, now)[0]["status"], "NEEDS_CONFIGURATION")

    def test_home_only_fatal_in_explicit_mode(self):
        runtime = doctor.check("container.homer", "PASS", "Ready")
        missing_home = doctor.check("home.accounts", "NEEDS_CONFIGURATION", "Unknown", module="home-baseline", scope="owner", method="manual")
        self.assertTrue(doctor.successful([runtime, missing_home]))
        self.assertFalse(doctor.successful([runtime, missing_home], True))

    def test_cli_missing_config_returns_valid_redacted_json(self):
        output = io.StringIO()
        with patch.object(doctor, "load_env", side_effect=doctor.ConfigError("secret-config-value")), contextlib.redirect_stdout(output):
            status = doctor.main(["--json", "--evidence", "/nonexistent/home-evidence.json"])
        payload = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertEqual(payload["schema_version"], 1)
        self.assertFalse(payload["runtime_ready"])
        self.assertFalse(payload["home_baseline_verified"])
        self.assertNotIn("secret-config-value", output.getvalue())
        for row in payload["checks"]:
            self.assertTrue({"id", "scope", "status", "method", "observed_at", "evidence", "next_action"}.issubset(row))

    def test_requested_runtime_reports_disabled_optional_skip(self):
        model = {"services": {"homer": {"ports": [{"target": 8080, "published": "8080"}]}}}
        with patch.object(doctor, "container_observation", return_value=(doctor.check("container.homer", "PASS", "ready"), "a" * 64, [])), patch.object(doctor, "http_observation", return_value=doctor.check("http.homer", "PASS", "ready")), patch.object(doctor, "disk_observations", return_value=[]):
            checks = doctor.collect({}, model, ["homer"])
        browser = next(c for c in checks if c["id"] == "container.webtop")
        self.assertEqual(browser["status"], "SKIP")
        self.assertFalse(browser["required"])


if __name__ == "__main__":
    unittest.main()
