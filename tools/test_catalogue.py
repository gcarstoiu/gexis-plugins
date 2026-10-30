# SPDX-License-Identifier: GPL-3.0-or-later
"""Run with the player's core on the path:
PYTHONPATH=<gexis-player>/core/src python -m pytest tools
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import tarfile

import pytest

import catalogue
import check
from catalogue import Invalid
from gexis_core import uploads

SOURCE = "https://github.com/someone/gexis-hello"


def archive(manifest: dict, run: bytes = b"#!/usr/bin/env python3\nprint('hello')\n") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in (("plugin.json", json.dumps(manifest).encode()), ("hello.py", run)):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


MANIFEST = {"id": "hello", "name": "Hello", "kind": "service", "version": "0.1.0", "run": "hello.py"}


def version(data: bytes, number: str = "0.1.0") -> dict:
    return {"version": number, "url": f"{SOURCE}/releases/download/v{number}/hello-{number}.tar.gz",
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "contract": 1, "player": "1.10.0"}


def entry(*versions: dict) -> dict:
    return {"id": "hello", "name": "Hello", "summary": "Says hello.", "kind": "service",
            "author": "someone", "source": SOURCE, "licence": "GPL-3.0-or-later",
            "versions": list(versions)}


def run(base, head, served: dict[str, bytes], path="plugins/hello.json"):
    def fetch(url, limit):
        return served[url]
    return check.check_entry(path, base, head, fetch=fetch, upload_check=uploads.check)


def test_a_new_listing_passes_when_its_archive_is_what_it_says():
    data = archive(MANIFEST)
    head = entry(version(data))
    done = run(None, head, {head["versions"][0]["url"]: data})
    assert any("upload check passes" in line for line in done)


def test_an_archive_that_differs_from_its_checksum_is_refused():
    data = archive(MANIFEST)
    head = entry(version(data))
    other = archive({**MANIFEST, "name": "Hello"}, run=b"#!/bin/sh\necho changed\n")
    head["versions"][0]["size"] = len(other)
    with pytest.raises(Invalid, match="sha256"):
        run(None, head, {head["versions"][0]["url"]: other})


def test_an_archive_of_another_size_is_refused():
    data = archive(MANIFEST)
    head = entry(version(data))
    head["versions"][0]["size"] += 1
    with pytest.raises(Invalid, match="bytes, not"):
        run(None, head, {head["versions"][0]["url"]: data})


def test_what_the_player_would_refuse_as_an_upload_is_refused():
    data = archive({**MANIFEST, "unit": "mine.service"})
    head = entry(version(data))
    with pytest.raises(Invalid, match="would refuse it"):
        run(None, head, {head["versions"][0]["url"]: data})


def test_the_manifest_must_say_what_the_entry_says():
    data = archive({**MANIFEST, "version": "0.2.0"})
    head = entry(version(data))
    with pytest.raises(Invalid, match="plugin.json says version"):
        run(None, head, {head["versions"][0]["url"]: data})


@pytest.mark.parametrize("plugin_id", ["spotify", "airplay", "gexis-extra"])
def test_the_players_own_ids_are_never_listed(plugin_id):
    with pytest.raises(Invalid, match="belongs to the player"):
        catalogue.validate({**entry(version(archive(MANIFEST))), "id": plugin_id})


def test_an_archive_from_anywhere_but_the_source_repository_is_refused():
    v = version(archive(MANIFEST))
    v["url"] = "https://example.com/hello-0.1.0.tar.gz"
    with pytest.raises(Invalid, match="release of"):
        catalogue.validate(entry(v))


def test_a_listed_version_never_changes_and_is_never_removed():
    first = archive(MANIFEST)
    base = entry(version(first))
    changed = copy.deepcopy(base)
    changed["versions"][0]["sha256"] = "0" * 64
    with pytest.raises(Invalid, match="sha256 cannot change"):
        run(base, changed, {})
    second = archive({**MANIFEST, "version": "0.2.0"})
    removed = entry(version(second, "0.2.0"))
    with pytest.raises(Invalid, match="not removed"):
        run(base, removed, {})


def test_a_new_version_is_checked_and_the_listed_one_is_not_downloaded_again():
    first = archive(MANIFEST)
    second = archive({**MANIFEST, "version": "0.2.0"})
    base = entry(version(first))
    head = entry(version(first), version(second, "0.2.0"))
    done = run(base, head, {head["versions"][1]["url"]: second})
    assert len([line for line in done if "downloaded" in line]) == 1


def test_withdrawing_a_listed_version_needs_no_download():
    base = entry(version(archive(MANIFEST)))
    head = copy.deepcopy(base)
    head["versions"][0]["withdrawn"] = "Plays nothing on 1.10.0; 0.2.0 fixes it."
    assert run(base, head, {})


def test_withdrawn_and_blocked_together_are_refused():
    with pytest.raises(Invalid, match="not both"):
        catalogue.validate({**entry(version(archive(MANIFEST))), "withdrawn": "a", "blocked": "b"})


@pytest.mark.parametrize("path", ["README.md", "tools/check.py", "plugins/sub/hello.json"])
def test_a_listing_changes_nothing_but_its_entry(path):
    with pytest.raises(Invalid, match="only plugins"):
        run(None, entry(version(archive(MANIFEST))), {}, path=path)


def test_a_listed_plugin_is_never_deleted():
    with pytest.raises(Invalid, match="never deleted"):
        run(entry(version(archive(MANIFEST))), None, {})


def test_the_file_is_named_after_the_id():
    with pytest.raises(Invalid, match="named hello.json"):
        catalogue.validate(entry(version(archive(MANIFEST))), "plugins/other.json")


def test_the_index_holds_every_entry_by_id_with_its_serial(tmp_path):
    for plugin_id in ("zeta", "alpha"):
        e = {**entry(version(archive(MANIFEST))), "id": plugin_id}
        (tmp_path / f"{plugin_id}.json").write_text(json.dumps(e))
    built = catalogue.index(catalogue.load(tmp_path), 7, "2026-10-29T00:00:00Z")
    assert built["serial"] == 7 and built["format"] == 1
    assert [p["id"] for p in built["plugins"]] == ["alpha", "zeta"]
    with pytest.raises(ValueError):
        catalogue.index([], 0)


def test_a_new_version_goes_after_the_listed_ones():
    first = archive(MANIFEST)
    second = archive({**MANIFEST, "version": "0.2.0"})
    base = entry(version(first))
    head = entry(version(second, "0.2.0"), version(first))
    with pytest.raises(Invalid, match="oldest first"):
        run(base, head, {head["versions"][0]["url"]: second})



def test_a_version_lists_exactly_the_permissions_its_plugin_asks_for():
    data = archive({**MANIFEST, "permissions": ["cec"]})
    listed = {**version(data), "permissions": ["cec"]}
    done = run(None, entry(listed), {listed["url"]: data})
    assert any("upload check passes" in line for line in done)
    hidden = version(data)
    with pytest.raises(Invalid, match="asks for"):
        run(None, entry(hidden), {hidden["url"]: data})


def test_a_listed_version_s_permissions_never_change():
    data = archive({**MANIFEST, "permissions": ["cec"]})
    listed = {**version(data), "permissions": ["cec"]}
    base = entry(listed)
    head = entry({**listed, "permissions": ["cec", "usb"]})
    with pytest.raises(Invalid, match="cannot change"):
        run(base, head, {})


def test_the_area_is_the_manifest_s():
    data = archive({**MANIFEST, "area": "library"})
    head = {**entry(version(data)), "area": "library"}
    run(None, head, {head["versions"][0]["url"]: data})
    with pytest.raises(Invalid, match="area"):
        run(None, entry(version(data)), {head["versions"][0]["url"]: data})
    with pytest.raises(Invalid, match="'area' must be one of"):
        catalogue.validate({**head, "area": "kitchen"}, "hello.json")
