import os
import shutil
import subprocess
import re

def find_binary(name, base_dir=None):
    """Locate binary in local directory, subdirectories, or system PATH."""
    search_paths = []
    if base_dir:
        search_paths.extend([
            base_dir,
            os.path.join(base_dir, "scrcpy"),
            os.path.join(base_dir, "bin"),
            os.path.join(base_dir, "..", "scrcpy")
        ])
    for p in search_paths:
        target = os.path.join(p, name)
        if os.path.exists(target):
            return target
    # Check system PATH
    sys_path = shutil.which(name)
    if sys_path:
        return sys_path
    return name

class DeviceManager:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.adb_exe = find_binary("adb.exe", self.base_dir)
        self.scrcpy_exe = find_binary("scrcpy.exe", self.base_dir)
        self.ffmpeg_exe = find_binary("ffmpeg.exe", self.base_dir)
        self._camera_cache = {}

    def get_connected_devices(self):
        """Returns a list of connected Android devices: [{'serial': ..., 'name': ...}]."""
        devices = []
        try:
            out = subprocess.check_output(
                [self.adb_exe, "devices", "-l"],
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            for line in out.strip().splitlines()[1:]:
                if "device" in line and not line.startswith("*"):
                    parts = line.split()
                    serial = parts[0]
                    # Query model and brand
                    try:
                        brand = subprocess.check_output(
                            [self.adb_exe, "-s", serial, "shell", "getprop", "ro.product.brand"],
                            text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        ).strip().capitalize()
                        model = subprocess.check_output(
                            [self.adb_exe, "-s", serial, "shell", "getprop", "ro.product.model"],
                            text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        ).strip()
                        name = f"{brand} {model}" if brand else model
                    except Exception:
                        name = serial
                    devices.append({"serial": serial, "name": name})
        except Exception:
            pass
        return devices

    def get_device_cameras(self, serial=None, force_refresh=False):
        """Discovers all physical cameras on the specified device with caching."""
        cache_key = serial or "default"
        if not force_refresh and cache_key in self._camera_cache:
            return self._camera_cache[cache_key]
        cmd = [self.scrcpy_exe]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["--video-source=camera", "--list-cameras"])

        cams = []
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            for line in res.stdout.splitlines() + res.stderr.splitlines():
                m = re.search(r"--camera-id=(\d+)\s+\(([^,]+),\s*(\d+)x(\d+)", line)
                if m:
                    cam_id, facing, w, h = m.groups()
                    w, h = int(w), int(h)
                    is_uw = "0," in line or "0." in line
                    
                    if facing == "front":
                        label = f"🤳 Frontal / Selfie (ID {cam_id})"
                    elif is_uw or "wide" in line.lower():
                        label = f"🔭 Ultra-Wide 0.6x (ID {cam_id})"
                    elif w >= 3840:
                        label = f"📸 Traseira Principal Alta Definição (ID {cam_id})"
                    else:
                        label = f"📷 Traseira Secundária (ID {cam_id})"

                    cams.append({
                        "id": cam_id,
                        "facing": facing,
                        "width": w,
                        "height": h,
                        "label": label
                    })
        except Exception:
            pass

        # Fallback if discovery fails or empty
        if not cams:
            cams = [
                {"id": "1", "facing": "front", "label": "🤳 Câmera Frontal (Padrão)"},
                {"id": "0", "facing": "back", "label": "📸 Câmera Traseira (Padrão)"}
            ]
        self._camera_cache[cache_key] = cams
        return cams
