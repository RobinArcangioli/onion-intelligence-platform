"""Simulate pg_dump -> age -> remote SSH commit without network or real data."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'backup-offsite.sh'


class OfflineBackupFlowTest(unittest.TestCase):
    def run_flow(self, database_fails):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            root = temp / 'workspace'
            (root / 'deploy/ovh').mkdir(parents=True)
            shutil.copy2(SOURCE, root / 'deploy/ovh/backup-offsite.sh')
            (root / '.env').write_text('OIP_EXAMPLE=ignored\n')
            bin_dir = temp / 'bin'
            bin_dir.mkdir()
            # No real database, Tor, age encryption or SSH is invoked by this test.
            docker = '#!/bin/sh\nprintf "synthetic database stream"\n' + ('exit 8\n' if database_fails else 'exit 0\n')
            age = '#!/bin/sh\ncat\n'
            ssh = '#!/bin/bash\ncmd="${@: -1}"\nbash -c "$cmd"\n'
            for command, source in [('docker', docker), ('age', age), ('ssh', ssh)]:
                stub = bin_dir / command
                stub.write_text(source)
                stub.chmod(0o700)
            destination = temp / 'remote'
            env = dict(os.environ)
            env.update({
                'PATH': str(bin_dir) + ':' + env['PATH'],
                'OIP_BACKUP_RECIPIENT': 'age1syntheticnotreal',
                'OIP_BACKUP_SSH_TARGET': 'backup@fake',
                'OIP_BACKUP_REMOTE_DIR': str(destination),
            })
            proc = subprocess.run(['bash', str(root / 'deploy/ovh/backup-offsite.sh')],
                                  text=True, capture_output=True, env=env)
            published = list(destination.glob('*.dump.age')) if destination.exists() else []
            if database_fails:
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(published, [])
                self.assertEqual(list(destination.glob('.*.partial.*')), [])
            else:
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(len(published), 1)
                self.assertEqual(published[0].read_bytes(), b'synthetic database stream')
                self.assertEqual(list(destination.glob('.*.partial.*')), [])

    def test_success_commits_archive_only_after_complete_stream(self):
        self.run_flow(database_fails=False)

    def test_failed_pg_dump_never_publishes_archive(self):
        self.run_flow(database_fails=True)


if __name__ == '__main__':
    unittest.main()
