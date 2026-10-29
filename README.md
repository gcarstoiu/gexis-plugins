# Gexis Player plugin catalogue

The plugins by other authors that [Gexis Player](https://github.com/gcarstoiu/gexis-player)
offers under **Settings → Plugins → More plugins**.

**Listed means checked, not made or vouched for.** Every version passes the
checks below and is read by a person before players can install it. A plugin
here is not part of Gexis Player: it is installed and run at the user's own
risk and responsibility, under the sandbox the player gives every plugin it
did not ship itself (its own temporary user, the system read-only, 1 GB of
memory; see *Writing a plugin*, section 3).

The decision behind it is
[ADR-0168](https://github.com/gcarstoiu/gexis-player/blob/main/docs/decisions/0168-a-plugin-catalogue.md).

## Getting a plugin listed

1. **Write the plugin** as
   [*Writing a plugin for Gexis Player*](https://github.com/gcarstoiu/gexis-player/blob/main/docs/WRITING-A-PLUGIN.md)
   describes, and package it as the `.tar.gz` it shows.
2. **Publish the archive on a GitHub release** of the plugin's public source
   repository.
3. **Open a pull request here adding `plugins/<id>.json`** - one plugin per
   pull request, and nothing else in it:

   ```json
   {
     "id": "hello",
     "name": "Hello",
     "summary": "Says hello in the player's log once a minute.",
     "kind": "service",
     "author": "your-github-name",
     "source": "https://github.com/your-github-name/gexis-hello",
     "licence": "GPL-3.0-or-later",
     "versions": [
       {
         "version": "0.1.0",
         "url": "https://github.com/your-github-name/gexis-hello/releases/download/v0.1.0/hello-0.1.0.tar.gz",
         "sha256": "…the archive's SHA-256…",
         "size": 1234,
         "contract": 1,
         "player": "1.10.0"
       }
     ]
   }
   ```
4. **The checks run** on the pull request (below). Fix what they report and
   push again.
5. **A person reads it**: the source at the release's tag against the
   summary, what it asks of the player, and a name that does not pass for
   Gexis Player's own or someone else's product. The pull request is merged
   after that reading, and the catalogue is published soon after.

## The fields

| Field | What it holds |
|---|---|
| `id` | The plugin's id, as in its `plugin.json`: a-z, 0-9 and `-`, starting with a letter, up to 31 characters. The file is named after it. The player's own ids, and any starting with `gexis`, are not available. |
| `name` | As in `plugin.json`; at most 40 characters. |
| `summary` | One line on what it does, at most 140 characters, shown in *More plugins*. |
| `kind` | `renderer` or `service`, as in `plugin.json`. |
| `author` | Your GitHub user name. |
| `source` | The plugin's public repository, `https://github.com/<owner>/<repo>`. |
| `licence` | The plugin's licence, as an SPDX expression. |
| `versions` | Every listed version, oldest first. |
| `versions[].version` | As in that archive's `plugin.json`. |
| `versions[].url` | The `.tar.gz` on a release of `source`. |
| `versions[].sha256`, `size` | The archive's SHA-256 (lower-case hex) and size in bytes, at most 200 MB. |
| `versions[].contract` | The plugin contract it speaks: `1`. |
| `versions[].player` | The lowest Gexis Player release it needs. |

## What the checks do

- The entry's form, as the table says.
- Each new version is downloaded from its `url`; its size and SHA-256 must
  match the entry.
- **The player's own upload check** runs on it - the same code a player runs
  when a plugin is uploaded - so a listed version is one a player would
  accept. Its `plugin.json` must carry the entry's id, name, kind and version.
- A version once listed never changes and is never removed, so the bytes a
  player installs are the bytes that were read.

The checks run this repository's own tools as they are on `main`; nothing
from the pull request is run.

## A new version

Add it to `versions` in a pull request, leaving the earlier ones as they
are. It is checked and read as the first one was; players offer it as an
update once it is published.

## Withdrawn and blocked

A version or a whole plugin can be **withdrawn** - no longer offered, and
marked on a player that has it, which keeps running it - or **blocked**, for
a plugin found to do harm: also switched off on every player that has it.
Each carries its reason, shown to the user.

## How the catalogue reaches players

After a merge the catalogue is published as `catalogue.json` with its
signature, on this repository's release
[`index`](https://github.com/gcarstoiu/gexis-plugins/releases/tag/index).
Each publish carries a serial one higher than the last. A player checks the
signature against the catalogue key it carries and refuses a serial lower
than one it has seen, so an older catalogue cannot be passed off as the
current one.

## For the maintainer

- `tools/catalogue.py` - an entry's form, and the index.
- `tools/check.py` - the pull request's check (`.github/workflows/check.yml`).
- `tools/publish.sh` - publishes after a merge, signed with the catalogue
  key; `--dry-run` builds and signs into `out/` only.
- `tools/player-ref` - the commit of Gexis Player whose upload check runs.
- Tests: `PYTHONPATH=tools:<gexis-player>/core/src python -m pytest tools`.

## Licence

This repository - its tools and the entries - is under the GNU General
Public License, version 3 or later ([LICENSE](LICENSE)). A listed plugin
keeps its own licence, the one its entry names.
