# SPDX-License-Identifier: GPL-3.0-or-later
"""The catalogue's entries and its index (gcarstoiu/gexis-player, ADR-0168).

    catalogue.py validate plugins/<id>.json ...   check entries' form
    catalogue.py index <plugins dir> <serial>     print catalogue.json

Standard library only: the pull request check runs it as it stands.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

#: The player's own rules (`gexis_core.plugins.ID`, `gexis_core.uploads.VERSION`).
ID = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+~-]{0,39}$")
KINDS = ("renderer", "service")
RELEASE = re.compile(r"^\d+\.\d+\.\d+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
AUTHOR = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
SOURCE = re.compile(r"^https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
SPDX = re.compile(r"^[A-Za-z0-9.+-]+(?: (?:AND|OR|WITH) [A-Za-z0-9.+-]+)*$")
#: The player's own plugins. Never listed, nor any id starting with "gexis".
RESERVED = frozenset({
    "airplay", "beszel", "beszel-hub", "bluetooth", "lms", "lyrion-server", "plexamp", "spotify",
})
#: What an archive may weigh (`gexis_core.uploads.MAX_BYTES`).
MAX_BYTES = 200 * 1024 * 1024
CONTRACTS = (1,)
FIELDS = {"id", "name", "summary", "kind", "author", "source", "licence", "versions", "withdrawn", "blocked"}
VERSION_FIELDS = {"version", "url", "sha256", "size", "contract", "player", "withdrawn", "blocked"}
#: What a version is, once listed: never changed afterwards.
PINNED = ("version", "url", "sha256", "size", "contract", "player")
FORMAT = 1


class Invalid(ValueError):
    """Why an entry cannot be listed, in words its author can act on."""


def _text(obj: dict, key: str, limit: int, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise Invalid(f"{where}: {key!r} is missing")
    if len(value) > limit or value != value.strip() or "\n" in value:
        raise Invalid(f"{where}: {key!r} must be one line of at most {limit} characters")
    return value


def _pulled(obj: dict, where: str) -> None:
    for key in ("withdrawn", "blocked"):
        if key in obj:
            _text(obj, key, 200, where)
    if "withdrawn" in obj and "blocked" in obj:
        raise Invalid(f"{where}: withdrawn or blocked, not both")


def validate(entry: object, filename: str | None = None) -> dict:
    """An entry's form, before anything is downloaded."""
    if not isinstance(entry, dict):
        raise Invalid("the entry is not a JSON object")
    where = filename or "entry"
    unknown = set(entry) - FIELDS
    if unknown:
        raise Invalid(f"{where}: unknown fields {sorted(unknown)}")
    plugin_id = _text(entry, "id", 31, where)
    if not ID.match(plugin_id):
        raise Invalid(f"{where}: {plugin_id!r} is not a usable id (a-z, 0-9 and -, starting with a letter)")
    if plugin_id in RESERVED or plugin_id.startswith("gexis"):
        raise Invalid(f"{where}: {plugin_id!r} belongs to the player")
    if filename is not None and Path(filename).name != f"{plugin_id}.json":
        raise Invalid(f"{where}: the file must be named {plugin_id}.json")
    _text(entry, "name", 40, where)
    _text(entry, "summary", 140, where)
    if entry.get("kind") not in KINDS:
        raise Invalid(f"{where}: 'kind' must be one of {KINDS}")
    if not AUTHOR.match(str(entry.get("author", ""))):
        raise Invalid(f"{where}: 'author' must be a GitHub user name")
    source = _text(entry, "source", 200, where)
    if not SOURCE.match(source):
        raise Invalid(f"{where}: 'source' must be a public repository, https://github.com/<owner>/<repo>")
    if not SPDX.match(_text(entry, "licence", 80, where)):
        raise Invalid(f"{where}: 'licence' must be an SPDX expression, such as GPL-3.0-or-later")
    _pulled(entry, where)
    versions = entry.get("versions")
    if not isinstance(versions, list) or not versions:
        raise Invalid(f"{where}: 'versions' must list at least one version")
    seen = set()
    for i, v in enumerate(versions):
        at = f"{where}: versions[{i}]"
        if not isinstance(v, dict):
            raise Invalid(f"{at} is not an object")
        unknown = set(v) - VERSION_FIELDS
        if unknown:
            raise Invalid(f"{at}: unknown fields {sorted(unknown)}")
        version = _text(v, "version", 40, at)
        if not VERSION.match(version):
            raise Invalid(f"{at}: {version!r} is not a usable version")
        if version in seen:
            raise Invalid(f"{at}: version {version} is listed twice")
        seen.add(version)
        url = _text(v, "url", 400, at)
        if not (url.startswith(f"{source}/releases/download/") and url.endswith(".tar.gz")):
            raise Invalid(f"{at}: 'url' must be a .tar.gz on a release of {source}")
        if not SHA256.match(str(v.get("sha256", ""))):
            raise Invalid(f"{at}: 'sha256' must be 64 lower-case hex characters")
        size = v.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_BYTES:
            raise Invalid(f"{at}: 'size' must be the archive's size in bytes, at most 200 MB")
        if v.get("contract") not in CONTRACTS:
            raise Invalid(f"{at}: 'contract' must be one of {CONTRACTS}")
        if not RELEASE.match(str(v.get("player", ""))):
            raise Invalid(f"{at}: 'player' must be the lowest Gexis Player release it needs, such as 1.10.0")
        _pulled(v, at)
    return entry


def load(directory: Path) -> list[dict]:
    entries = []
    for path in sorted(directory.glob("*.json")):
        entries.append(validate(json.loads(path.read_text()), path.name))
    return entries


def index(entries: list[dict], serial: int, date: str | None = None) -> dict:
    """The file the player reads. Its serial only increases (ADR-0168, as
    the player's channel files do)."""
    if not isinstance(serial, int) or serial < 1:
        raise ValueError("the serial starts at 1")
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"format": FORMAT, "serial": serial, "date": date,
            "plugins": sorted(entries, key=lambda e: e["id"])}


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "validate":
        for name in argv[1:]:
            try:
                validate(json.loads(Path(name).read_text()), name)
            except (Invalid, ValueError) as exc:
                print(f"refused: {exc}")
                return 1
            print(f"ok: {name}")
        return 0
    if len(argv) == 3 and argv[0] == "index":
        print(json.dumps(index(load(Path(argv[1])), int(argv[2])), indent=1, ensure_ascii=False))
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
