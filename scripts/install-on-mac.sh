#!/bin/bash
# Installs a KeyFinder update package on a Mac by hand, for versions without Install from Zip (before 1.3.2): it replaces the interface (app.asar).
# The analysis engine inside the app stays as it is; the version replaced is kept in KeyFinder's versions folder, so Profile ▸ Updates ▸ Go Back can return to it.
# Your library, songs and settings aren't touched.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
NEW="$HERE/app.asar"
NEW_HASH="@HASH@"
VERSION="@VERSION@"

APP=""
for candidate in "/Applications/KeyFinder.app" "$HOME/Applications/KeyFinder.app"; do
  if [ -d "$candidate" ]; then APP="$candidate"; break; fi
done
if [ -z "$APP" ]; then
  echo "Couldn't find KeyFinder.app in /Applications or ~/Applications."
  exit 1
fi
if [ ! -f "$NEW" ]; then
  echo "app.asar is missing: run this from the unzipped update folder."
  exit 1
fi

RES="$APP/Contents/Resources"
PLIST="$APP/Contents/Info.plist"
OLD_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$PLIST" 2>/dev/null || echo '?')"
echo "Updating $APP from $OLD_VERSION to $VERSION"

# Quit KeyFinder (and its engine) first.
if pgrep -xq KeyFinder; then
  echo "Quitting KeyFinder…"
  osascript -e 'quit app "KeyFinder"' || true
  for _ in $(seq 1 20); do pgrep -xq KeyFinder || break; sleep 0.5; done
  pkill -x KeyFinder 2>/dev/null || true
  sleep 1
fi

# Use sudo only if the app isn't yours to change.
SUDO=""
if [ ! -w "$RES" ]; then
  echo "KeyFinder.app belongs to another user; your password is needed to update it."
  SUDO="sudo"
fi

# Keep the version being replaced where KeyFinder (1.3.2 and later) looks for it, so
# Profile ▸ Updates ▸ Go Back can put it back.
VERSIONS="$HOME/Library/Application Support/KeyFinder/versions"
mkdir -p "$VERSIONS"
rm -rf "$VERSIONS/previous.tmp" && mkdir -p "$VERSIONS/previous.tmp"
cp "$RES/app.asar" "$VERSIONS/previous.tmp/app.asar"
rm -rf "$VERSIONS/previous" && mv "$VERSIONS/previous.tmp" "$VERSIONS/previous"
printf '{"version":"%s","kind":"interface","savedAt":%s000,"replacedBy":"%s"}' "$OLD_VERSION" "$(date +%s)" "$VERSION" > "$VERSIONS/previous.json"
BACKUP="$VERSIONS/previous/app.asar"
echo "Kept $OLD_VERSION for Go Back (in $VERSIONS)"

$SUDO cp "$NEW" "$RES/app.asar"
$SUDO /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST"
$SUDO /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$PLIST"
# If the app records a fingerprint of its interface, record the new one.
if /usr/libexec/PlistBuddy -c 'Print :ElectronAsarIntegrity:Resources/app.asar:hash' "$PLIST" >/dev/null 2>&1; then
  $SUDO /usr/libexec/PlistBuddy -c "Set :ElectronAsarIntegrity:Resources/app.asar:hash $NEW_HASH" "$PLIST"
fi

# Sign it again as the release build does (ad hoc), so macOS still opens it.
echo "Re-signing…"
$SUDO codesign --force --deep --sign - "$APP"
$SUDO xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

echo "Done: KeyFinder is now $VERSION. Opening it…"
open "$APP"
echo
echo "To go back to $OLD_VERSION: Profile ▸ Updates ▸ Go Back in KeyFinder, or in Terminal:"
echo "  cp \"$BACKUP\" \"$RES/app.asar\" && codesign --force --deep --sign - \"$APP\""
