// The scripts that swap KeyFinder's versions (packages.ts): each waits for KeyFinder to quit, keeps
// what's there as the previous version, puts the new one in, records how it went and opens KeyFinder
// again. They read everything from KF_* environment variables, set in packages.ts startSwap(), and
// have no Electron in them, so scripts/check-swap-scripts.mjs can run them on their own (in CI, on
// Windows, macOS and Linux).
//
//   KF_PID       KeyFinder's process, to wait for          KF_KIND     interface | bundle | dir | installer
//   KF_ACTION    update | revert                            KF_TARGET   what's replaced
//   KF_SOURCE    what goes in                               KF_PREV     where the previous version is kept
//   KF_PREV_PAYLOAD  its name in there                      KF_META     previous.json's text, KF_META_FILE its path
//   KF_RESULT    the result file                            KF_LOCK     removed when done
//   KF_VERSION   the version going in                       KF_HASH     app.asar's header hash (macOS)
//   KF_BUNDLE    the .app (macOS, else empty)               KF_EXE      what to open afterwards (not macOS)

// macOS and Linux. Copies or moves into place, never deletes what's there until the new one is in.
export const POSIX_SCRIPT = String.raw`
NOTE=""
# macOS can stop an app changing apps until it's allowed to; say where, if a step fails there.
HINT=""
[ -n "$KF_BUNDLE" ] && HINT=" If macOS asked about KeyFinder changing apps, allow it in System Settings > Privacy & Security > App Management, then try again."
while kill -0 "$KF_PID" 2>/dev/null; do sleep 0.2; done
sleep 0.5
TMP="$KF_PREV.tmp"
json() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
finish() {
  printf '{"ok":%s,"action":"%s","version":"%s","message":"%s"}' "$1" "$KF_ACTION" "$KF_VERSION" "$(json "$2")" > "$KF_RESULT"
  rm -f "$KF_LOCK"
  if [ -n "$KF_BUNDLE" ]; then open "$KF_BUNDLE"; else nohup "$KF_EXE" >/dev/null 2>&1 & fi
  exit 0
}
rm -rf "$TMP" && mkdir -p "$TMP" || finish false "Couldn't make room to keep the current version."
case "$KF_KIND" in
  interface)
    cp "$KF_TARGET" "$TMP/$KF_PREV_PAYLOAD" || finish false "Couldn't keep the current version, so nothing was changed.$HINT"
    cp "$KF_SOURCE" "$KF_TARGET.new" || { rm -f "$KF_TARGET.new"; finish false "Couldn't copy the new version in, so nothing was changed.$HINT"; }
    mv -f "$KF_TARGET.new" "$KF_TARGET" || { rm -f "$KF_TARGET.new"; finish false "Couldn't put the new version in place, so nothing was changed.$HINT"; }
    if [ -n "$KF_BUNDLE" ]; then
      PL="$KF_BUNDLE/Contents/Info.plist"
      /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $KF_VERSION" "$PL" 2>/dev/null
      /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $KF_VERSION" "$PL" 2>/dev/null
      if [ -n "$KF_HASH" ] && /usr/libexec/PlistBuddy -c "Print :ElectronAsarIntegrity:Resources/app.asar:hash" "$PL" >/dev/null 2>&1; then
        /usr/libexec/PlistBuddy -c "Set :ElectronAsarIntegrity:Resources/app.asar:hash $KF_HASH" "$PL"
      fi
      if ! codesign --force --deep --sign - "$KF_BUNDLE" >/dev/null 2>&1; then
        NOTE="macOS couldn't sign KeyFinder again. If it won't open, run: codesign --force --deep --sign - \"$KF_BUNDLE\""
      fi
    fi
    ;;
  bundle)
    mv "$KF_TARGET" "$TMP/$KF_PREV_PAYLOAD" || finish false "Couldn't move the current version aside, so nothing was changed.$HINT"
    if ! mv "$KF_SOURCE" "$KF_TARGET"; then
      mv "$TMP/$KF_PREV_PAYLOAD" "$KF_TARGET"
      finish false "Couldn't put the new version in place, so the current one was put back.$HINT"
    fi
    xattr -dr com.apple.quarantine "$KF_TARGET" 2>/dev/null
    ;;
  *)
    finish false "This kind of update can't be installed on this computer."
    ;;
esac
rm -rf "$KF_PREV" && mv "$TMP" "$KF_PREV" && printf '%s' "$KF_META" > "$KF_META_FILE"
finish true "$NOTE"
`

// Windows. interface: swap app.asar; dir: swap the install folder; installer: keep the folder, then run it.
export const WINDOWS_SCRIPT = String.raw`
$ErrorActionPreference = 'Stop'
try { Wait-Process -Id ([int]$env:KF_PID) -Timeout 60 } catch {}
Start-Sleep -Milliseconds 500
$tmp = "$($env:KF_PREV).tmp"
function Finish($ok, $msg) {
  $r = @{ ok = $ok; action = $env:KF_ACTION; version = $env:KF_VERSION; message = $msg } | ConvertTo-Json -Compress
  [IO.File]::WriteAllText($env:KF_RESULT, $r)
  Remove-Item -Force -ErrorAction SilentlyContinue $env:KF_LOCK
  if ($env:KF_KIND -ne 'installer' -or -not $ok) { Start-Process -FilePath $env:KF_EXE }
  exit 0
}
function Keep() {
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $env:KF_PREV
  Move-Item $tmp $env:KF_PREV
  [IO.File]::WriteAllText($env:KF_META_FILE, $env:KF_META)
}
try {
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $tmp
  New-Item -ItemType Directory -Force $tmp | Out-Null
} catch { Finish $false "Couldn't make room to keep the current version." }
switch ($env:KF_KIND) {
  'interface' {
    try { Copy-Item $env:KF_TARGET (Join-Path $tmp $env:KF_PREV_PAYLOAD) } catch { Finish $false "Couldn't keep the current version, so nothing was changed." }
    try { Copy-Item $env:KF_SOURCE "$($env:KF_TARGET).new"; Move-Item -Force "$($env:KF_TARGET).new" $env:KF_TARGET }
    catch { Remove-Item -Force -ErrorAction SilentlyContinue "$($env:KF_TARGET).new"; Finish $false "Couldn't put the new version in place, so nothing was changed." }
    Keep; Finish $true ''
  }
  'dir' {
    $keep = Join-Path $tmp $env:KF_PREV_PAYLOAD
    robocopy $env:KF_TARGET $keep /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Finish $false "Couldn't keep the current version, so nothing was changed." }
    robocopy $env:KF_SOURCE $env:KF_TARGET /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) {
      robocopy $keep $env:KF_TARGET /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
      Finish $false "Couldn't put the previous version in place, so the current one was put back."
    }
    Keep; Finish $true ''
  }
  'installer' {
    $keep = Join-Path $tmp $env:KF_PREV_PAYLOAD
    robocopy $env:KF_TARGET $keep /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    $kept = $LASTEXITCODE -lt 8
    $p = Start-Process -FilePath $env:KF_SOURCE -ArgumentList '/S','--updated','--force-run' -PassThru -Wait
    if ($p.ExitCode -ne 0) { Finish $false "The installer stopped (code $($p.ExitCode)); KeyFinder wasn't changed." }
    if ($kept) { Keep }
    Finish $true ''
  }
}
Finish $false "This kind of update can't be installed on this computer."
`
