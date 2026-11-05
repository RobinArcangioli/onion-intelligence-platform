"""Private ingress M7-A policy check; tests do not modify running services."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CONF = ROOT / 'infrastructure/nginx/default.conf'


class NginxSecurityPolicyTests(unittest.TestCase):
    def test_private_host_and_no_public_docs(self):
        content = CONF.read_text()
        self.assertIn('if ($host !~ ^(localhost|127\\.0\\.0\\.1)$) { return 421; }', content)
        for path in ('/docs', '/redoc', '/openapi.json'):
            self.assertIn(f'location = {path} {{ return 404; }}', content)
        self.assertIn('listen 8080;', content)
        self.assertIn('access_log off;', content)

    def test_headers_inherited_on_errors(self):
        content = CONF.read_text()
        for key in ('Content-Security-Policy', 'Cache-Control', 'X-Frame-Options',
                    'Permissions-Policy', 'Cross-Origin-Resource-Policy'):
            self.assertIn(f'add_header {key} ', content)
        # Nginx's location-level add_header overrides server-level inheritance.
        self.assertNotIn('        add_header ', content)
        self.assertIn('limit_req zone=oip_api burst=30 nodelay;', content)

    @unittest.skipUnless(shutil.which('nginx'), 'nginx not installed')
    def test_nginx_syntax_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            # Replace only the Docker DNS name for a standalone syntax check.
            # The actual production config remains unchanged.
            (temp / 'site.conf').write_text(
                CONF.read_text().replace('proxy_pass http://api:8000;',
                                         'proxy_pass http://127.0.0.1:8000;')
            )
            (temp / 'nginx.conf').write_text(
                'events {}\nhttp {\ninclude ' + str(temp / 'site.conf') + ';\n}\n'
            )
            result = subprocess.run(
                ['nginx', '-t', '-p', str(temp), '-c', str(temp / 'nginx.conf')],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
