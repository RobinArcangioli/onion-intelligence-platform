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
            with self.assertRaisesRegex(RuntimeError, 'Tor/collection'):
                monitor.check_containers()

    def test_freshness_disabled_is_not_a_recovery_claim(self):
        self.assertEqual(monitor.check_backup(require=False), 'NOT_ENABLED')

    def test_freshness_missing_and_stale_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            stamp = Path(directory) / 'stamp'
            with self.assertRaisesRegex(RuntimeError, 'missing'):
                monitor.check_backup(require=True, stamp=stamp)
            stamp.touch()
            with patch.object(monitor.time, 'time', return_value=stamp.stat().st_mtime + 37 * 3600):
                with self.assertRaisesRegex(RuntimeError, 'stale'):
                    monitor.check_backup(require=True, stamp=stamp)

    def test_monitor_external_urls_never_used(self):
        code = (ROOT / 'monitor.py').read_text()
        self.assertIn('ProxyHandler({})', code)
        self.assertIn('http://127.0.0.1:8000', code)

    def test_systemd_is_opt_in(self):
        installer = (ROOT / 'install-systemd.sh').read_text()
        self.assertNotIn('systemctl enable', installer)
        unit = (ROOT / 'systemd/oip-monitor.service').read_text()
        self.assertIn('Environment=OIP_MONITOR_REQUIRE_BACKUP=0', unit)
        backup = (ROOT / 'systemd/oip-backup.service').read_text()
        self.assertIn('EnvironmentFile=/etc/oip/backup.env', backup)
        self.assertNotIn('OIP_TOR_COLLECTION_ENABLED', backup)

    def test_backup_requires_full_success_before_freshness_stamp(self):
        script = (ROOT / 'backup-offsite.sh').read_text()
        self.assertLess(script.index('remote_commit='), script.index('last-backup-ok'))
        self.assertIn('remote_partial=', script)
        self.assertIn('mv -n --', script)
        self.assertIn('set -Eeuo pipefail', script)
        self.assertIn('StrictHostKeyChecking=yes', script)
        self.assertIn('pg_dump', script)
        self.assertIn('age -r', script)

    def test_recovery_has_no_network_or_persistent_volume(self):
        script = (ROOT / 'verify-restore.sh').read_text()
        self.assertIn('--network none', script)
        self.assertIn('--single-transaction', script)
        self.assertIn('trap cleanup EXIT', script)
        self.assertNotIn('down -v', script)

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
