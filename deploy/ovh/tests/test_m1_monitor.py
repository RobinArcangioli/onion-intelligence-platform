"""Offline M1 regression tests: no Docker, SSH or Internet calls."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('oip_ovh_monitor', ROOT / 'monitor.py')
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def docker_fixture(published_gateway=None, failed_health=None, extra=()):
    running = [f'{monitor.PROJECT}-{name}-1' for name in monitor.SERVICES] + list(extra)

    def mock_docker(*args):
        if args[0] == 'ps':
            return '\n'.join(running)
        name = args[-1]
        service = name.split('-')[-2]
        if '.State' in args[2]:
            return json.dumps({'Running': True, 'Health': {'Status': ('unhealthy' if failed_health == service else 'healthy')}})
        if '.NetworkSettings.Ports' in args[2]:
            ports = {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8000'}] if published_gateway is None else published_gateway} if service == 'gateway' else {'5432/tcp': None}
            return json.dumps(ports)
        raise AssertionError(args)
    return mock_docker


class MonitorUnitTest(unittest.TestCase):
    def test_healthy_private_core(self):
        with patch.object(monitor, 'docker', side_effect=docker_fixture()):
            monitor.check_containers()

    def test_public_gateway_fails(self):
        with patch.object(monitor, 'docker', side_effect=docker_fixture(
            published_gateway=[{'HostIp': '0.0.0.0', 'HostPort': '8000'}])):
            with self.assertRaisesRegex(RuntimeError, 'not private'):
                monitor.check_containers()

    def test_unhealthy_database_fails(self):
        with patch.object(monitor, 'docker', side_effect=docker_fixture(failed_health='db')):
            with self.assertRaisesRegex(RuntimeError, 'db unhealthy'):
                monitor.check_containers()

    def test_running_tor_fails(self):
        with patch.object(monitor, 'docker', side_effect=docker_fixture(
            extra=['onion-intelligence-platform-queue_worker-1'])):
            with self.assertRaisesRegex(RuntimeError, 'profile mismatch'):
                monitor.check_containers()

    def test_manual_worker_required_and_scheduler_forbidden(self):
        services = [f"{monitor.PROJECT}-{name}-1" for name in monitor.WORKER_SERVICES]
        with patch.object(monitor, "docker", side_effect=docker_fixture(extra=services)):
            monitor.check_containers("manual")
        with patch.object(monitor, "docker", side_effect=docker_fixture(extra=services[:1])):
            with self.assertRaisesRegex(RuntimeError, "queue_worker not running"):
                monitor.check_containers("manual")
        with patch.object(monitor, "docker", side_effect=docker_fixture(
            extra=services + [f"{monitor.PROJECT}-scheduler-1"],
        )):
            with self.assertRaisesRegex(RuntimeError, "scheduler"):
                monitor.check_containers("manual")

    def test_warning_becomes_alert_on_next_check_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "health.json"
            failure = {"QUEUE_LEASE_EXPIRED": "expired lease"}
            self.assertEqual(monitor.report(failure, state), 0)
            self.assertEqual(monitor.report(failure, state), 1)
            self.assertEqual(monitor.report({}, state), 0)
            self.assertEqual(monitor.report(failure, state), 0)

    def test_monitor_external_urls_never_used(self):
        code = (ROOT / 'monitor.py').read_text()
        self.assertIn('ProxyHandler({})', code)
        self.assertIn('http://127.0.0.1:8000', code)

    def test_systemd_is_opt_in(self):
        installer = (ROOT / 'install-systemd.sh').read_text()
        self.assertNotIn('systemctl enable', installer)
        unit = (ROOT / 'systemd/oip-monitor.service').read_text()
        self.assertIn("Environment=OIP_MONITOR_PROFILE=private", unit)
        self.assertIn("StateDirectory=oip-monitor", unit)
        self.assertNotIn("OnFailure", unit)
        self.assertNotIn("oip-backup", installer)
        self.assertFalse((ROOT / "backup-offsite.sh").exists())
        self.assertFalse((ROOT / "systemd/oip-backup.timer").exists())

    def test_ci_has_no_deploy_or_secrets(self):
        workflow = (ROOT.parents[1] / '.github/workflows/oip-ci.yml').read_text()
        self.assertIn('contents: read', workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertNotIn('secrets.', workflow)
        self.assertNotIn('ssh ', workflow)
        self.assertNotIn('deploy.sh deploy', workflow)
        self.assertNotIn('--profile tor', workflow)


if __name__ == '__main__':
    unittest.main()
