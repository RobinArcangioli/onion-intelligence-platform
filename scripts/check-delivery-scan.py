#!/usr/bin/env python3
"""Verify scanner coverage and apply the OIP release severity policy."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys


def package_key(name, version):
    return re.sub(r"[-_.]+", "-", name).lower(), version


def check_lock_coverage(directory, results):
    npm_lock = json.loads((directory / "package-lock.json").read_text())["packages"]
    npm_locked = {
        (package.get("name", path.rsplit("node_modules/", 1)[-1]), package["version"])
        for path, package in npm_lock.items()
        if path
    }
    npm_inventoried = {
        (package["Name"], package["Version"])
        for result in results
        if result["Type"] == "npm"
        for package in result.get("Packages", [])
    }
    missing = npm_locked - npm_inventoried
    if not npm_locked or missing:
        raise ValueError(f"incomplete npm inventory: {sorted(missing)}")

    for scope in ("build", "runtime", "test"):
        locked = {
            package_key(*line.split("=="))
            for line in (directory / scope / "requirements.txt").read_text().splitlines()
        }
        inventoried = {
            package_key(package["Name"], package["Version"])
            for result in results
            if result["Target"].endswith(f"{scope}/requirements.txt")
            for package in result.get("Packages", [])
        }
        missing = locked - inventoried
        if not locked or missing:
            raise ValueError(f"incomplete Python inventory for {scope}: {sorted(missing)}")


def main(lock_directory, reports):
    print(f"Delivery advisory gate at {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    blocking = set()
    review = set()
    for index, path in enumerate(reports):
        results = json.loads(path.read_text())["Results"]
        if index == 0:
            check_lock_coverage(lock_directory, results)
        elif not any(result.get("Class") == "os-pkgs" and result.get("Packages") for result in results):
            raise ValueError(f"OS inventory absent from {path.name}")

        package_count = sum(len(result.get("Packages", [])) for result in results)
        findings = 0
        for result in results:
            for item in result.get("Vulnerabilities", []):
                severity = item.get("Severity", "UNKNOWN").upper()
                finding = (
                    severity, item["VulnerabilityID"], item["PkgName"], item["InstalledVersion"]
                )
                findings += 1
                if severity in {"HIGH", "CRITICAL"}:
                    blocking.add(finding)
                elif severity not in {"LOW", "MEDIUM"}:
                    review.add(finding)

        print(f"{path.name}: {package_count} inventory entries, {findings} advisory matches")

    for finding in sorted(review):
        print("REVIEW:", *finding)
    for finding in sorted(blocking):
        print("BLOCKED:", *finding)
    print(f"{len(blocking)} unique blocking findings; {len(review)} unique findings to review")
    return bool(blocking)


if __name__ == "__main__":
    try:
        sys.exit(main(Path(sys.argv[1]), [Path(path) for path in sys.argv[2:]]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(f"BLOCKED: invalid or incomplete advisory report: {exc}")
