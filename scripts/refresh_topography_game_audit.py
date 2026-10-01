"""Refresh reports/topography_game_audit.json (native topography types and the file hash) after a game update.

The geography export refuses to run when the vanilla topography file no longer matches this audit. Parsed with
the project's Clausewitz parser, so run it from the constructor environment:

    uv run --project ../ProsperOrPerishConstructor python scripts/refresh_topography_game_audit.py
"""
import hashlib
import json
import tomllib
from pathlib import Path

from eu5gameparser.clausewitz.parser import parse_file

ROOT = Path(__file__).resolve().parents[1]


def plain(value):
    if hasattr(value, "entries"):
        out = {}
        for e in value.entries:
            if getattr(e, "key", None) is None:
                continue
            out[str(e.key)] = plain(e.value)
        return out
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(getattr(value, "name", None) or getattr(value, "tag", None) or value.__class__.__name__)


def main():
    game = Path(tomllib.loads((ROOT / "geography_test.local.toml").read_text())["paths"]["game_root"]) / "game"
    source = game / "in_game/common/topography/00_default.txt"
    doc = parse_file(source)
    types = {str(e.key): plain(e.value) for e in doc.entries}
    report = {"source": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "parser": "eu5gameparser.clausewitz.parser.parse_file", "types": types}
    (ROOT / "reports/topography_game_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"types": len(types), "sha256": report["sha256"]}))


if __name__ == "__main__":
    main()
