# SPDX-License-Identifier: GPL-3.0-or-later
"""The check on a pull request that lists a plugin (ADR-0168).

    check.py --repo <checkout> --base <ref> --head <ref> --player <gexis-player's core/src>

The pull request's files are read as data (`git show`), never run: what
runs is this repository's own tools at its base and the player's own upload
check, `gexis_core.uploads.check`, at the commit in `tools/player-ref`. A
version that passes is one the player would accept as an upload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalogue  # noqa: E402
from catalogue import Invalid  # noqa: E402

Fetch = Callable[[str, int], bytes]


def fetch(url: str, limit: int) -> bytes:
    """The archive, refused once it passes `limit` bytes."""
    request = urllib.request.Request(url, headers={"User-Agent": "gexis-plugins-check"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise Invalid(f"{url} is larger than {limit} bytes")
    return data


def check_path(path: str) -> None:
    parts = PurePosixPath(path).parts
    if len(parts) != 2 or parts[0] != "plugins" or not parts[1].endswith(".json"):
        raise Invalid(f"{path}: a listing changes only plugins/<id>.json")


def check_entry(path: str, base: dict | None, head: dict | None, *, fetch: Fetch,
                upload_check: Callable) -> list[str]:
    """One changed file: what was checked, or `Invalid` for why not."""
    check_path(path)
    if head is None:
        raise Invalid(f"{path}: a listed plugin is withdrawn or blocked, never deleted")
    catalogue.validate(head, path)
    done = [f"{path}: the entry's form"]
    old = {v["version"]: v for v in (base or {}).get("versions", [])}
    new = {v["version"]: v for v in head["versions"]}
    if base is not None:
        if base["id"] != head["id"]:
            raise Invalid(f"{path}: the id never changes")
        for version, before in old.items():
            after = new.get(version)
            if after is None:
                raise Invalid(f"{path}: version {version} is listed; it can be withdrawn, not removed")
            changed = [k for k in catalogue.PINNED if before.get(k) != after.get(k)]
            if changed:
                raise Invalid(f"{path}: version {version} is listed; {', '.join(changed)} cannot change")
    for version, v in new.items():
        if version in old:
            continue
        archive = fetch(v["url"], catalogue.MAX_BYTES)
        if len(archive) != v["size"]:
            raise Invalid(f"{path}: {version}'s archive is {len(archive)} bytes, not {v['size']}")
        digest = hashlib.sha256(archive).hexdigest()
        if digest != v["sha256"]:
            raise Invalid(f"{path}: {version}'s archive has sha256 {digest}, not the one listed")
        try:
            checked = upload_check(archive, ours=set(catalogue.RESERVED), installed={})
        except ValueError as exc:
            raise Invalid(f"{path}: {version}: the player would refuse it: {exc}") from None
        manifest = checked.manifest
        for key, want in (("id", head["id"]), ("name", head["name"]), ("kind", head["kind"]),
                          ("version", version)):
            if manifest.get(key) != want:
                raise Invalid(f"{path}: {version}: plugin.json says {key} {manifest.get(key)!r}, the entry {want!r}")
        done.append(f"{path}: {version} downloaded, {len(archive)} bytes, sha256 matches, the player's upload check passes")
    return done


def _show(repo: str, ref: str, path: str) -> dict | None:
    out = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"], capture_output=True)
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        raise Invalid(f"{path} is not readable JSON") from None


def changed(repo: str, base: str, head: str) -> list[str]:
    out = subprocess.run(["git", "-C", repo, "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}"],
                         capture_output=True, check=True)
    return [p.decode("utf-8", "replace") for p in out.stdout.split(b"\0") if p]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--player", required=True, help="gexis-player's core/src")
    args = parser.parse_args(argv)
    sys.path.insert(0, args.player)
    from gexis_core import uploads

    paths = changed(args.repo, args.base, args.head)
    if not paths:
        print("refused: the pull request changes nothing")
        return 1
    try:
        for path in paths:
            check_path(path)
            base = _show(args.repo, args.base, path)
            head = _show(args.repo, args.head, path)
            for line in check_entry(path, base, head, fetch=fetch, upload_check=uploads.check):
                print(f"ok: {line}")
    except (Invalid, OSError) as exc:
        print(f"refused: {exc}")
        return 1
    print("Every check passed. A person reads the plugin before it is merged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
