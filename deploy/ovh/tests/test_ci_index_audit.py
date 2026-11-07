"""Offline test of the separate CI Git-index-only safety gate."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('ci_index_audit', ROOT / 'scripts' / 'ci-index-audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CIIndexAuditTest(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for name in ('.env.example', 'frontend/package-lock.json'):
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('placeholder\n')
        self.stage()
        self.rules = audit.load_rules()

    def stage(self):
        subprocess.run(['git', '-C', str(self.root), 'add', '-A'], check=True)

    def test_clean_index_passes(self):
        count, issues = audit.audit_index(self.root, self.rules)
        self.assertEqual(count, 2)
        self.assertFalse(issues)

    def test_forbidden_env_detected_without_reading_values(self):
        (self.root / '.env').write_text('SENSITIVE_DO_NOT_PRINT\n')
        self.stage()
        _, issues = audit.audit_index(self.root, self.rules)
        self.assertIn('forbidden tracked path: .env', issues)
        self.assertNotIn('SENSITIVE_DO_NOT_PRINT', str(issues))

    def test_token_detected_without_printing_token(self):
        token = 'ghp_' + ('z' * 30)
        (self.root / 'config.txt').write_text(token + '\n')
        self.stage()
        _, issues = audit.audit_index(self.root, self.rules)
        self.assertTrue(any('possible github-token' in x for x in issues))
        self.assertNotIn(token, str(issues))

    def test_gitlab_token_detected_without_printing_token(self):
        token = 'glpat-' + ('z' * 24)
        (self.root / 'config.txt').write_text(token + '\n')
        self.stage()
        _, issues = audit.audit_index(self.root, self.rules)
        self.assertTrue(any('possible gitlab-token' in x for x in issues))
        self.assertNotIn(token, str(issues))

    def test_private_paths_and_uninspectable_archives_block(self):
        paths = ('.ssh/config', '.aws/config', 'private/notes.txt',
                 'known_hosts.private', 'fixtures/data.tar.gz')
        for path in paths:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('synthetic fixture\n')
        self.stage()
        _, issues = audit.audit_index(self.root, self.rules)
        for path in paths:
            self.assertIn(f'forbidden tracked path: {path}', issues)

    def test_history_audit_detects_commit_and_annotated_tag_messages(self):
        scripts = self.root / 'scripts'
        scripts.mkdir()
        auditor = scripts / 'pre-push-audit.py'
        auditor.write_bytes(audit.AUDITOR_PATH.read_bytes())
        git = ['git', '-C', str(self.root), '-c', 'user.name=Fixture',
               '-c', 'user.email=fixture@example.test']
        commit_token = 'glpat-' + ('c' * 24)
        tag_token = 'glpat-' + ('t' * 24)
        subprocess.run([*git, 'commit', '-qm', commit_token], check=True)
        subprocess.run([*git, 'tag', '-a', 'fixture', '-m', tag_token], check=True)
        result = subprocess.run([sys.executable, auditor], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('possible gitlab-token in commit message', result.stdout)
        self.assertIn('possible gitlab-token in tag message', result.stdout)
        self.assertNotIn(commit_token, result.stdout + result.stderr)
        self.assertNotIn(tag_token, result.stdout + result.stderr)

    def test_missing_lockfile_blocks(self):
        (self.root / 'frontend/package-lock.json').unlink()
        self.stage()
        _, issues = audit.audit_index(self.root, self.rules)
        self.assertIn('missing required tracked file: frontend/package-lock.json', issues)


if __name__ == '__main__':
    unittest.main()
