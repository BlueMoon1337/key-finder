## Install KeyFinder

**macOS**
1. Download the file for your Mac (Apple menu ▸ About This Mac shows which):
   - Apple silicon (M1, M2, M3, M4…): `KeyFinder-…-arm64-mac.dmg`
   - Intel: `KeyFinder-…-x64-mac.dmg`
2. Open the `.dmg` and drag **KeyFinder** into **Applications**.
3. The app isn't signed with an Apple Developer ID, so the first time, **right-click KeyFinder ▸ Open**, then **Open** again (or **System Settings ▸ Privacy & Security ▸ Open Anyway**). After that it opens normally.
   - If macOS says the app "is damaged", run this once in Terminal, then open it: `xattr -dr com.apple.quarantine /Applications/KeyFinder.app`

**Windows (10 or 11, 64-bit)**
1. Download `KeyFinder-Setup-….exe` and run it.
2. The installer isn't signed with a Windows certificate, so SmartScreen may warn: choose **More info ▸ Run anyway**.
3. Pick where to install, and open KeyFinder from the Start menu.

**First use**
- Your library is kept in `Documents/KeyFinder Library`.
- The first song you split into stems downloads the Demucs model (about 80 MB, once). The 6-stem model downloads the first time you ask for 6 stems. You can download both ahead of time in **Profile ▸ Stem separation**.
- Stem separation runs on the GPU on Apple silicon Macs and on the CPU elsewhere; on a CPU, allow a few minutes per song.
- If the tempo shows half or double what you hear, use **½× / 2×** on the Tempo card.

