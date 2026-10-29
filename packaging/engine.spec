# PyInstaller spec for the desktop engine: a folder build (faster start-up than one file),
# copied into the Electron app as resources/engine by electron-builder.yml.
#
#   pyinstaller packaging/engine.spec --noconfirm   →  build/engine-dist/keyfinder-engine/
#
# Builds for the machine it runs on (macOS arm64 or x64, Windows x64), so the release workflow
# builds once per platform. It includes Demucs and PyTorch for neural stem separation; the
# models' weights aren't bundled but downloaded once, on first use (keyfinder/neural.py).

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("keyfinder")
    + collect_submodules("demucs")
    + ["av.audio.resampler", "av.filter", "multipart", "huggingface_hub", "safetensors.torch"]
)
# Demucs' model definitions (remote/*.yaml, files.txt) are read at run time.
datas = collect_data_files("demucs")

a = Analysis(
    ["keyfinder_engine.py"],
    pathex=[".."],
    hiddenimports=hiddenimports,
    datas=datas,
    # Training-only and unused heavy extras.
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "torchvision", "torchaudio", "tensorboard",
              "dora", "hydra", "submitit", "musdb", "museval"],
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
