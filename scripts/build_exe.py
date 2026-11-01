import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_MAIN = os.path.join(BASE_DIR, "src", "main.py")
ICON_ICO = os.path.join(BASE_DIR, "assets", "icon_on.ico")

cmd = [
    sys.executable,
    "-m", "PyInstaller",
    "--noconsole",
    "--onefile",
    "--name=AndroidWebcamPro",
    f"--icon={ICON_ICO}",
    f"--add-data={os.path.join(BASE_DIR, 'assets')};assets",
    f"--paths={os.path.join(BASE_DIR, 'src')}",
    SRC_MAIN
]

print("Building executable with PyInstaller...")
print("Command:", " ".join(cmd))
res = subprocess.run(cmd, cwd=BASE_DIR)
if res.returncode == 0:
    print("\nSUCCESS! Binary created at:")
    print(os.path.join(BASE_DIR, "dist", "AndroidWebcamPro.exe"))
else:
    print("\nBuild failed with code:", res.returncode)
