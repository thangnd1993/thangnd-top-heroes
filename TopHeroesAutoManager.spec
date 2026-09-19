# Build on Windows: pyinstaller --clean --noconfirm TopHeroesAutoManager.spec
from pathlib import Path

root = Path(SPECPATH)
a = Analysis([str(root / "run_app.py")], pathex=[str(root / "src")], binaries=[],
             datas=[(str(root / "assets" / "templates"), "assets/templates"),
                    (str(root / "assets" / "tasks"), "assets/tasks")],
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TopHeroesAutoManager",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="TopHeroesAutoManager")
