# PyInstaller spec for the desktop engine: a folder build (faster start-up than one file),
# copied into the Electron app as resources/engine by electron-builder.yml.
#
#   pyinstaller packaging/engine.spec --noconfirm   →  build/engine-dist/keyfinder-engine/
#
# Builds for the machine it runs on (macOS arm64 or x64, Windows x64), so the release workflow
# builds once per platform.

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("keyfinder")
    + ["av.audio.resampler", "av.filter", "multipart"]
)

a = Analysis(
    ["keyfinder_engine.py"],
    pathex=[".."],
    hiddenimports=hiddenimports,
    # Optional heavy extras: the neural separator is not bundled (it would add PyTorch, ~2 GB).
    excludes=["torch", "demucs", "tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="keyfinder-engine",
    console=True,  # stdin/stdout carry the ready line and the parent watch
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="keyfinder-engine", upx=False)
