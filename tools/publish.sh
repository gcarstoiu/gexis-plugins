#!/bin/bash
# Publish the catalogue (ADR-0168 in gcarstoiu/gexis-player): catalogue.json
# with a serial one past the published one, signed by the catalogue key,
# uploaded with its signature to this repository's release `index`, then read
# back and verified. Run locally after a merge, on the maintainer's say-so.
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
verify() { gpgv --quiet --keyring "$work/catalogue.gpg" "$1.sig" "$1"; }

serial=0
if [ "$DRY" = 0 ] && gh release view "$RELEASE" -R "$REPO" >/dev/null 2>&1; then
	mkdir "$work/published"
	gh release download "$RELEASE" -R "$REPO" -p catalogue.json -p catalogue.json.sig -D "$work/published"
	verify "$work/published/catalogue.json"
	serial=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["serial"])' "$work/published/catalogue.json")
fi

python3 tools/catalogue.py index plugins $((serial + 1)) > "$work/catalogue.json"
gpg --homedir "$GEXIS_CATALOGUE_GNUPGHOME" --batch --yes --local-user "$SIGNER" \
	--detach-sign --output "$work/catalogue.json.sig" "$work/catalogue.json"
verify "$work/catalogue.json"
echo "catalogue.json: serial $((serial + 1)), $(python3 -c 'import json, sys; print(len(json.load(open(sys.argv[1]))["plugins"]))' "$work/catalogue.json") plugins, signature good"

if [ "$DRY" = 1 ]; then
	mkdir -p out && cp "$work/catalogue.json" "$work/catalogue.json.sig" out/
	echo "dry run: out/catalogue.json and its signature; nothing uploaded"
	exit 0
fi

gh release view "$RELEASE" -R "$REPO" >/dev/null 2>&1 ||
	gh release create "$RELEASE" -R "$REPO" --title "Catalogue index" --latest=false \
		--notes "catalogue.json and its signature, read by Gexis Player. Replaced on every publish."
gh release upload "$RELEASE" -R "$REPO" --clobber "$work/catalogue.json" "$work/catalogue.json.sig"

# GitHub's public URL is cached for minutes after an upload: read back through gh.
mkdir "$work/back"
gh release download "$RELEASE" -R "$REPO" -p catalogue.json -p catalogue.json.sig -D "$work/back"
verify "$work/back/catalogue.json"
cmp -s "$work/back/catalogue.json" "$work/catalogue.json" || { echo "read back differs" >&2; exit 1; }
echo "published: serial $((serial + 1)), read back with a good signature"
