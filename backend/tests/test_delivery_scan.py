"""Exercise the delivery gate with synthetic advisory and inventory reports."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(os.environ.get("OIP_TEST_REPO_ROOT", Path(__file__).resolve().parents[2]))


@pytest.fixture
def delivery_reports(tmp_path):
    (tmp_path / "package-lock.json").write_text(json.dumps({
        "packages": {"": {}, "node_modules/fixture-js": {"version": "1.0"}}
    }))
    locks = [{"Target": "package-lock.json", "Type": "npm", "Packages": [
        {"Name": "fixture-js", "Version": "1.0"},
    ]}]
    for scope in ("build", "runtime", "test"):
        (tmp_path / scope).mkdir()
        (tmp_path / scope / "requirements.txt").write_text("fixture-python==2.0\n")
        locks.append({"Target": f"{scope}/requirements.txt", "Type": "pip", "Packages": [
            {"Name": "fixture_python", "Version": "2.0"},
        ]})
    return tmp_path, locks


def run_gate(directory, locks, findings):
    lock_report = directory / "locks.json"
    lock_report.write_text(json.dumps({"Results": locks}))
    image_report = directory / "image.json"
    image_report.write_text(json.dumps({"Results": [{
        "Class": "os-pkgs", "Packages": [{"Name": "fixture-os", "Version": "3.0"}],
        "Vulnerabilities": findings,
    }]}))
    return subprocess.run(
        [sys.executable, ROOT / "scripts/check-delivery-scan.py", directory, lock_report, image_report],
        capture_output=True, text=True, check=False,
    )


@pytest.mark.parametrize(("severity", "status", "message"), [
    ("CRITICAL", 1, "BLOCKED: CRITICAL"),
    ("HIGH", 1, "BLOCKED: HIGH"),
    ("UNKNOWN", 0, "REVIEW: UNKNOWN"),
    ("MEDIUM", 0, "0 unique blocking findings"),
])
def test_delivery_severity_policy(delivery_reports, severity, status, message):
    directory, locks = delivery_reports
    result = run_gate(directory, locks, [{
        "Severity": severity, "VulnerabilityID": "TEST-0001",
        "PkgName": "fixture-os", "InstalledVersion": "3.0",
    }])
    assert result.returncode == status
    assert message in result.stdout


def test_delivery_scan_fails_when_a_locked_package_is_missing(delivery_reports):
    directory, locks = delivery_reports
    result = run_gate(directory, locks[:-1], [])
    assert result.returncode == 1
    assert "incomplete Python inventory for test" in result.stderr
