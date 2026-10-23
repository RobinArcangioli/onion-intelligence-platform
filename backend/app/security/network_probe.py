"""Read-only, network-layer diagnostic from a disposable collector container.

Not part of the collector run path. Does not send traffic to an Onion host,
resolve public DNS or retrieve content. Exit nonzero if the Tor-only boundary
cannot be demonstrated from the actual collector network namespace.
"""
import socket
import sys


def reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    checks = [
        ("Tor SOCKS reachable", reachable("tor", 9050)),
        ("PostgreSQL reachable over private bridge", reachable("db", 5432)),
        ("Direct IPv4 HTTPS denied", not reachable("1.1.1.1", 443)),
        ("Direct IPv4 DNS denied", not reachable("8.8.8.8", 53)),
    ]
    for label, passed in checks:
        print(f'{"PASS" if passed else "FAIL"}: {label}', flush=True)
    return 0 if all(passed for _, passed in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
