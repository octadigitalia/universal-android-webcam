import os
import shutil
import subprocess
import sys
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_MAIN = os.path.join(BASE_DIR, "src", "main.py")
ICON_ICO = os.path.join(BASE_DIR, "assets", "icon_on.ico")
DRIVERS_DIR = os.path.join(BASE_DIR, "drivers")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

print("=" * 60)
print("  UNIVERSAL ANDROID WEBCAM PRO - BUILD & PACKAGING PIPELINE")
print("=" * 60)

# 1. Compile with PyInstaller
cmd = [
    sys.executable,
    "-m", "PyInstaller",
    "--noconsole",
    "--onefile",
    "--name=AndroidWebcamPro",
    f"--icon={ICON_ICO}",
    f"--add-data={ASSETS_DIR};assets",
    f"--add-data={DRIVERS_DIR};drivers",
    f"--paths={os.path.join(BASE_DIR, 'src')}",
    SRC_MAIN
]

print("\n[1/3] Compiling standalone executable with PyInstaller...")
res = subprocess.run(cmd, cwd=BASE_DIR)
if res.returncode != 0:
    print(f"\n❌ Build failed with exit code: {res.returncode}")
    sys.exit(res.returncode)

built_exe = os.path.join(BASE_DIR, "dist", "AndroidWebcamPro.exe")
if not os.path.exists(built_exe):
    print("❌ dist/AndroidWebcamPro.exe was not found!")
    sys.exit(1)

print("✅ Binary successfully created at:", built_exe)

# 2. Assemble release folder
RELEASE_DIR = os.path.join(BASE_DIR, "release", "AndroidWebcamPro-v1.0.0-win64")
print(f"\n[2/3] Assembling standalone distribution in:\n  {RELEASE_DIR}")
os.makedirs(RELEASE_DIR, exist_ok=True)

# Copy compiled executable
shutil.copy2(built_exe, os.path.join(RELEASE_DIR, "AndroidWebcamPro.exe"))

# Copy scrcpy folder if exists
src_scrcpy = os.path.join(BASE_DIR, "scrcpy")
if not os.path.exists(src_scrcpy):
    src_scrcpy = r"C:\GalaxyWebcam\scrcpy-win64-v5.0.1"
if os.path.exists(src_scrcpy):
    dst_scrcpy = os.path.join(RELEASE_DIR, "scrcpy")
    if os.path.exists(dst_scrcpy):
        shutil.rmtree(dst_scrcpy)
    shutil.copytree(src_scrcpy, dst_scrcpy)
    print("  + Bundled scrcpy & ADB")

# Copy ffmpeg.exe
src_ffmpeg = os.path.join(BASE_DIR, "ffmpeg.exe")
if not os.path.exists(src_ffmpeg):
    src_ffmpeg = r"C:\GalaxyWebcam\ffmpeg.exe"
if os.path.exists(src_ffmpeg):
    shutil.copy2(src_ffmpeg, os.path.join(RELEASE_DIR, "ffmpeg.exe"))
    print("  + Bundled FFmpeg static binary")

# Copy drivers folder
if os.path.exists(DRIVERS_DIR):
    dst_drivers = os.path.join(RELEASE_DIR, "drivers")
    if os.path.exists(dst_drivers):
        shutil.rmtree(dst_drivers)
    shutil.copytree(DRIVERS_DIR, dst_drivers)
    print("  + Bundled Virtual Camera & Virtual Microphone Drivers")

# Copy docs
for doc in ["README.md", "LICENSE"]:
    doc_path = os.path.join(BASE_DIR, doc)
    if os.path.exists(doc_path):
        shutil.copy2(doc_path, os.path.join(RELEASE_DIR, doc))

# 3. Create standalone zip package for GitHub Releases
ZIP_PATH = os.path.join(BASE_DIR, "release", "AndroidWebcamPro-v1.0.0-win64.zip")
print(f"\n[3/3] Creating GitHub Release ZIP package:\n  {ZIP_PATH}")
with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(RELEASE_DIR):
        for f in files:
            full_path = os.path.join(root, f)
            arcname = os.path.relpath(full_path, os.path.dirname(RELEASE_DIR))
            zipf.write(full_path, arcname)

print("\n" + "=" * 60)
print("🎉 BUILD COMPLETE!")
print(f"📦 Release ZIP: {ZIP_PATH} ({os.path.getsize(ZIP_PATH) // (1024*1024)} MB)")
print("Users on GitHub only need to download the ZIP, double-click")
print("AndroidWebcamPro.exe, and everything works seamlessly out of the box!")
print("=" * 60)
