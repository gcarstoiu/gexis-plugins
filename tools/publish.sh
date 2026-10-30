#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Publish the catalogue (ADR-0168 in gcarstoiu/gexis-player): catalogue.json
# with a serial one past the published one, signed by the catalogue key,
# uploaded with its signature to this repository's release `index`, then read
# back and verified. Run locally after a merge, on the maintainer's say-so.
# The signature is named by the serial (catalogue-<serial>.json.sig) and
# kept: GitHub's cache once served a new catalogue.json with the previous
# signature, and a player reads the one its catalogue's serial names.
#
#   GEXIS_CATALOGUE_GNUPGHOME=<key folder> tools/publish.sh            publish
#   GEXIS_CATALOGUE_GNUPGHOME=<key folder> tools/publish.sh --dry-run  build, sign and verify into ./out only
#
# The player verifies with the public key it carries (keys/gexis-catalogue.asc
# here, packaged with the player's core) and refuses a serial lower than one
# it has accepted.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO=gcarstoiu/gexis-plugins
RELEASE=index
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
: "${GEXIS_CATALOGUE_GNUPGHOME:?set it to the catalogue key folder}"
[ -s keys/gexis-catalogue.asc ] && [ -s keys/signer ] || { echo "keys/gexis-catalogue.asc and keys/signer are needed" >&2; exit 1; }
SIGNER="$(cat keys/signer)!"

if [ "$DRY" = 0 ]; then
	git fetch -q origin main
	[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "not at origin/main" >&2; exit 1; }
	[ -z "$(git status --porcelain)" ] || { echo "uncommitted changes" >&2; exit 1; }
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
gpg --dearmor < keys/gexis-catalogue.asc > "$work/catalogue.gpg"
sig() { echo "catalogue-$1.json.sig"; }
verify() { gpgv --quiet --keyring "$work/catalogue.gpg" "$2" "$1"; }
serial_of() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["serial"])' "$1"; }

# The published serial, in a dry run too: reading it changes nothing, and
# the dry run then signs what a publish would.
serial=0
if gh release view "$RELEASE" -R "$REPO" >/dev/null 2>&1; then
	mkdir "$work/published"
	gh release download "$RELEASE" -R "$REPO" -p catalogue.json -D "$work/published"
	serial=$(serial_of "$work/published/catalogue.json")
	gh release download "$RELEASE" -R "$REPO" -p "$(sig "$serial")" -D "$work/published"
	verify "$work/published/catalogue.json" "$work/published/$(sig "$serial")"
fi

next=$((serial + 1))
python3 tools/catalogue.py index plugins "$next" > "$work/catalogue.json"
gpg --homedir "$GEXIS_CATALOGUE_GNUPGHOME" --batch --yes --local-user "$SIGNER" \
	--detach-sign --output "$work/$(sig "$next")" "$work/catalogue.json"
verify "$work/catalogue.json" "$work/$(sig "$next")"
echo "catalogue.json: serial $next, $(python3 -c 'import json, sys; print(len(json.load(open(sys.argv[1]))["plugins"]))' "$work/catalogue.json") plugins, signature good"

if [ "$DRY" = 1 ]; then
	mkdir -p out && cp "$work/catalogue.json" "$work/$(sig "$next")" out/
	echo "dry run: out/catalogue.json and its signature; nothing uploaded"
	exit 0
fi

gh release view "$RELEASE" -R "$REPO" >/dev/null 2>&1 ||
	gh release create "$RELEASE" -R "$REPO" --title "Catalogue index" --latest=false \
		--notes "catalogue.json, replaced on every publish, and each serial's signature, read by Gexis Player."
gh release upload "$RELEASE" -R "$REPO" --clobber "$work/catalogue.json" "$work/$(sig "$next")"

# GitHub's public URL is cached for minutes after an upload: read back through gh.
mkdir "$work/back"
gh release download "$RELEASE" -R "$REPO" -p catalogue.json -p "$(sig "$next")" -D "$work/back"
verify "$work/back/catalogue.json" "$work/back/$(sig "$next")"
cmp -s "$work/back/catalogue.json" "$work/catalogue.json" || { echo "read back differs" >&2; exit 1; }
echo "published: serial $next, read back with a good signature"
