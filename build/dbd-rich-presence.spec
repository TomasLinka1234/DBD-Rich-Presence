# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: jeden soubor DbD-Rich-Presence.exe bez okna konzole.
#   pyinstaller --noconfirm --clean build/dbd-rich-presence.spec
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
APP = os.path.join(ROOT, "app")
# RapidOCR umí i jiné výpočetní knihovny; stačí onnxruntime.
SKIP = ("pytorch", "paddle", "openvino", "tensorrt", "mnn")

datas = [(os.path.join(APP, f), "app") for f in ("dbd_data.json", "ikona.png", "ikona.ico")]
datas += collect_data_files("rapidocr", excludes=["**/pytorch/**"])

hiddenimports = collect_submodules("rapidocr", filter=lambda name: not any(s in name for s in SKIP))
hiddenimports += ["pystray._win32"]

a = Analysis(
    [os.path.join(APP, "main.py")],
    pathex=[APP],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "paddle", "openvino", "tensorrt", "MNN", "tkinter", "matplotlib", "IPython", "pytest",
              "scipy", "pandas", "sympy", "lxml", "cryptography", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DbD-Rich-Presence",
    console=False,
    icon=os.path.join(APP, "ikona.ico"),
    upx=False,
    runtime_tmpdir=None,
)
