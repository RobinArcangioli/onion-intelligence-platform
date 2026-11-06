#!/usr/bin/env python3
"""Register an OIP URL handler for a locally installed Tor Browser on Linux."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.security.onion import canonical_onion_page


def desktop_argument(value: Path) -> str:
    value = str(value)
    if any(ord(char) < 32 for char in value):
        raise ValueError("Chemin de lanceur invalide")
    escaped = value.replace("\\", "\\\\\\\\").replace('"', '\\\\"').replace("$", "\\\\$").replace(chr(96), "\\\\" + chr(96))
    return '"' + escaped.replace("%", "%%") + '"'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, required=True, help="Lanceur start-tor-browser exécutable")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("uri", nargs="?")
    args = parser.parse_args()
    browser = args.browser.expanduser().absolute()
    if not browser.is_file() or not os.access(browser, os.X_OK):
        parser.error("Choisis un lanceur Tor Browser exécutable.")
    if args.install:
        directory = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "applications"
        directory.mkdir(parents=True, exist_ok=True)
        desktop = directory / "oip-tor-browser.desktop"
        command = " ".join((desktop_argument(Path(sys.executable)), desktop_argument(Path(__file__).resolve()),
                            "--browser", desktop_argument(browser), "%u"))
        desktop.write_text(f"[Desktop Entry]\nType=Application\nName=OIP – Tor Browser\nExec={command}\n"
                           "NoDisplay=true\nMimeType=x-scheme-handler/oip-tor;\n", encoding="utf-8")
        subprocess.run(["xdg-mime", "default", desktop.name, "x-scheme-handler/oip-tor"], check=True)
        return
    if not args.uri or not args.uri.startswith("oip-tor:"):
        parser.error("Lien OIP Tor invalide.")
    try:
        url = canonical_onion_page(unquote(args.uri.removeprefix("oip-tor:"), errors="strict"))
    except ValueError:
        parser.error("URL Onion invalide.")
    os.execv(browser, [str(browser), url])


if __name__ == "__main__":
    main()
