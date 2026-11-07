#!/usr/bin/env python3
"""Fail-closed checks of RESOLVED Compose JSON; never echo environment secrets.

Run as `docker compose ... config --format json | python3 check_compose.py`.
Do not save the resolved configuration in a file or expose it in CI logs.
"""
import argparse
import json
import sys

CORE = {"db", "api", "gateway"}
TOR = {"tor", "collector", "queue_worker"}


def _require(condition: bool, msg: str) -> None:
    if not condition:
        raise ValueError(msg)


def validate(obj: dict, profile: str = "private") -> None:
    _require(profile in ("private", "manual"), "unknown profile")
    services = obj["services"]
    networks = obj["networks"]
    _require(CORE <= services.keys(), "missing core service")
    _require(set(services) <= CORE | TOR, "unreviewed service in deployment")

    for name, service in services.items():
        _require(not service.get("privileged"), f"{name} is privileged")
        _require(service.get("network_mode") != "host", f"{name} uses host network")
        _require(not service.get("devices"), f"{name} has device access")
        _require(not service.get("pid") == "host", f"{name} uses host PID namespace")
        _require(not service.get("ports") or name == "gateway", f"{name} publishes a port")
        _require(
            "docker.sock" not in json.dumps(service.get("volumes", [])),
            f"{name} has Docker socket access",
        )
        if name in TOR:
            _require("tor" in service.get("profiles", []), f"{name} isn't behind tor profile")

    gateway_ports = services["gateway"].get("ports", [])
    _require(len(gateway_ports) == 1, "gateway must bind exactly one host port")
    binding = gateway_ports[0]
    _require(
        binding.get("host_ip") == "127.0.0.1"
        and str(binding.get("published")) == "8000"
        and int(binding.get("target", 0)) == 8080
        and binding.get("protocol", "tcp") == "tcp",
        "gateway must bind only 127.0.0.1:8000 -> 8080/tcp",
    )
    _require(
        set(services["db"].get("networks", {})) == {"private"}
        and set(services["api"].get("networks", {})) == {"private"}
        and set(services["gateway"].get("networks", {})) == {"private", "ingress"},
        "unexpected core network attachment",
    )
    private = [v for name, v in networks.items() if name == "private" or name.endswith("_private")]
    _require(bool(private) and all(net.get("internal") is True for net in private), "private network not internal")

    db_env = services["db"].get("environment", {})
    api_env = services["api"].get("environment", {})
    _require(api_env.get("OIP_LEGACY_API_KEY_ENABLED", "false").lower() == "false", "legacy API key enabled")
    expected = "true" if profile == "manual" else "false"
    _require(api_env.get("OIP_MANUAL_COLLECTION_ENABLED") == expected, "manual enqueue gate does not match profile")
    if profile == "manual":
        _require({"tor", "queue_worker"} <= services.keys(), "manual profile requires Tor and queue worker")
        worker = services["queue_worker"]
        _require(worker.get("environment", {}).get("OIP_TOR_COLLECTION_ENABLED") == "true",
                 "worker Tor gate is disabled")
        _require(set(worker.get("networks", {})) == {"private", "tor_proxy"}, "unexpected worker network")
        _require(set(services["tor"].get("networks", {})) == {"tor_proxy", "tor_egress"}, "unexpected Tor network")
        _require(networks.get("tor_proxy", {}).get("internal") is True, "Tor proxy network not internal")
        _require(worker.get("read_only") is True and "ALL" in worker.get("cap_drop", []),
                 "worker filesystem or capabilities are not restricted")
    _require(api_env.get("OIP_TOR_COLLECTION_ENABLED") == "false", "Tor collection gate not disabled")
    password = db_env.get("POSTGRES_PASSWORD", "")
    key = api_env.get("OIP_API_KEY", "")
    _require(
        len(password) >= 24 and len(key) >= 32
        and not password.startswith("replace_with_") and not key.startswith("replace_with_"),
        "secret is unset or looks like a placeholder",
    )
    _require(services["api"].get("read_only") is True, "API filesystem must be read-only")
    _require(services["gateway"].get("read_only") is True, "gateway filesystem must be read-only")
    for name in CORE:
        _require(
            "ALL" in services[name].get("cap_drop", []) if name != "db" else True,
            f"{name} must drop Linux capabilities",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("private", "manual"), default="private")
    args = parser.parse_args()
    try:
        validate(json.load(sys.stdin), args.profile)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, AttributeError) as exc:
        print(f"NO-GO: OVH Compose check: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: Compose {args.profile} profile checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
