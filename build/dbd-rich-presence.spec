# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: jeden soubor DbD-Rich-Presence.exe bez okna konzole.
#   pyinstaller --noconfirm --clean build/dbd-rich-presence.spec
import os
import re

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
APP = os.path.join(ROOT, "app")
# RapidOCR umí i jiné výpočetní knihovny; stačí onnxruntime.
SKIP = ("pytorch", "paddle", "openvino", "tensorrt", "mnn")

# Vlastnosti souboru (pravé tlačítko -> Vlastnosti -> Podrobnosti); jen při sestavení ve Windows
with open(os.path.join(APP, "version.py"), encoding="utf-8") as f:
    VERSION = re.search(r'VERSION = "([^"]+)"', f.read()).group(1)
NUMS = tuple(([int(x) for x in VERSION.split(".")] + [0, 0, 0, 0])[:4])
try:
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
except ImportError:
    version_info = None
else:
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=NUMS, prodvers=NUMS),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "TomasLinka1234 (open source)"),
                StringStruct("FileDescription", "DbD Rich Presence - Discord status pro Dead by Daylight"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "DbD-Rich-Presence"),
                StringStruct("LegalCopyright", "(c) 2026 TomasLinka1234, MIT License"),
                StringStruct("OriginalFilename", "DbD-Rich-Presence.exe"),
                StringStruct("ProductName", "DbD Rich Presence"),
                StringStruct("ProductVersion", VERSION),
                StringStruct("Comments", "Zdrojový kód: https://github.com/TomasLinka1234/DBD-Rich-Presence"),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

datas = [(os.path.join(APP, f), "app") for f in ("dbd_data.json", "ikona.png", "ikona.ico")]
datas += [(os.path.join(APP, "ui", "index.html"), os.path.join("app", "ui"))]     # vzhled okna aplikace
datas += collect_data_files("rapidocr", excludes=["**/pytorch/**"])

hiddenimports = collect_submodules("rapidocr", filter=lambda name: not any(s in name for s in SKIP))
hiddenimports += ["pystray._win32"]
# Okno aplikace: pywebview přes WinForms + Edge WebView2 (pythonnet = clr). Ostatní platformy pywebview nejsou potřeba.
hiddenimports += ["webview.platforms.winforms", "webview.platforms.edgechromium", "clr"]
WEBVIEW_SKIP = ["webview.platforms.gtk", "webview.platforms.qt", "webview.platforms.cocoa", "webview.platforms.cef",
                "webview.platforms.android", "webview.platforms.mshtml", "qtpy", "gi", "cefpython3", "objc"]

a = Analysis(
    [os.path.join(APP, "main.py")],
    pathex=[APP],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=WEBVIEW_SKIP + ["torch", "paddle", "openvino", "tensorrt", "MNN", "tkinter", "matplotlib", "IPython", "pytest",
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
    version=version_info,
    upx=False,
    runtime_tmpdir=None,
)
