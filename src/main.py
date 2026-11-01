import os
import sys
import time
import datetime
import subprocess
import threading
import ctypes

# Determine base directory whether running from script or PyInstaller frozen bundle
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure logs don't fail when running without console
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
if sys.stdout is None:
    sys.stdout = open(os.path.join(LOGS_DIR, "app.log"), "a", encoding="utf-8", buffering=1)
if sys.stderr is None:
    sys.stderr = open(os.path.join(LOGS_DIR, "error.log"), "a", encoding="utf-8", buffering=1)

from PIL import Image
import pystray
from pystray import MenuItem as item, Menu

try:
    from pynput import keyboard
except ImportError:
    keyboard = None

from discovery import DeviceManager, find_binary

RECORDINGS_DIR = os.path.join(os.path.expanduser("~"), "Videos", "AndroidWebcam")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Locate icons
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
ICON_OFF_PATH = os.path.join(ASSETS_DIR, "icon_off.png")
ICON_ON_PATH = os.path.join(ASSETS_DIR, "icon_on.png")

# Fallback icons if not present
if not os.path.exists(ICON_OFF_PATH):
    ICON_OFF_PATH = os.path.join(BASE_DIR, "icon_off.png")
    ICON_ON_PATH = os.path.join(BASE_DIR, "icon_on.png")

OBS_DIR = r"C:\Program Files\obs-studio\bin\64bit"
OBS_EXE = os.path.join(OBS_DIR, "obs64.exe")

class UniversalWebcamApp:
    def __init__(self):
        self.device_mgr = DeviceManager(BASE_DIR)
        self.is_running = False
        self.scrcpy_proc = None
        self.obs_proc = None

        # State
        self.selected_device = None  # serial
        self.device_name = "Android"
        self.available_cameras = []
        self.camera_id = "1"
        self.resolution = "1280x720"
        self.fps = "30"
        self.zoom = "1.0"

        # Toggles
        self.is_mirrored = True
        self.is_desk_view = False
        self.use_mic = False
        self.torch_on = False
        self.is_muted = False
        self.is_recording = False
        self.current_record_file = None

        self.icon_off = Image.open(ICON_OFF_PATH) if os.path.exists(ICON_OFF_PATH) else None
        self.icon_on = Image.open(ICON_ON_PATH) if os.path.exists(ICON_ON_PATH) else None
        self.tray_icon = None
        self.hotkeys_listener = None

    def refresh_devices_and_cameras(self):
        """Scans for connected devices and cameras."""
        devices = self.device_mgr.get_connected_devices()
        if devices:
            if not self.selected_device or not any(d['serial'] == self.selected_device for d in devices):
                self.selected_device = devices[0]['serial']
                self.device_name = devices[0]['name']
            self.available_cameras = self.device_mgr.get_device_cameras(self.selected_device)
            # Default to front camera if available
            front_cams = [c for c in self.available_cameras if c.get('facing') == 'front']
            if front_cams and self.camera_id not in [c['id'] for c in self.available_cameras]:
                self.camera_id = front_cams[0]['id']
        else:
            self.selected_device = None
            self.device_name = "Nenhum celular conectado"
            self.available_cameras = []

    def clean_obs_safemode(self):
        safe_mode_file = os.path.expandvars(r"%APPDATA%\obs-studio\safe_mode")
        if os.path.exists(safe_mode_file):
            try:
                os.remove(safe_mode_file)
            except Exception:
                pass

    def get_orientation_flag(self):
        if self.is_desk_view:
            return "flip180" if self.is_mirrored else "180"
        else:
            return "flip0" if self.is_mirrored else "0"

    def build_scrcpy_command(self):
        cmd = [
            self.device_mgr.scrcpy_exe,
            "--video-source=camera",
            f"--camera-id={self.camera_id}",
            f"--camera-size={self.resolution}",
            f"--camera-fps={self.fps}",
            f"--capture-orientation={self.get_orientation_flag()}",
            "--window-title=GalaxyCam"
        ]

        if self.selected_device:
            cmd.extend(["-s", self.selected_device])

        if self.zoom != "1.0":
            cmd.append(f"--camera-zoom={self.zoom}")

        if self.torch_on:
            cmd.append("--camera-torch")

        if self.use_mic:
            cmd.extend(["--audio-source=mic", "--audio-codec=opus"])
        else:
            cmd.append("--no-audio")

        if self.is_recording:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.current_record_file = os.path.join(RECORDINGS_DIR, f"Webcam_{timestamp}.mp4")
            cmd.append(f"--record={self.current_record_file}")

        return cmd

    def start_camera(self):
        if self.is_running:
            return

        self.refresh_devices_and_cameras()
        if not self.selected_device:
            self.notify("Dispositivo não detectado", "Conecte o smartphone via USB e ative a Depuração USB.")
            return

        self.clean_obs_safemode()
        cmd_scrcpy = self.build_scrcpy_command()

        try:
            self.scrcpy_proc = subprocess.Popen(
                cmd_scrcpy,
                cwd=os.path.dirname(self.device_mgr.scrcpy_exe)
            )
        except Exception as e:
            self.notify("Erro ao iniciar câmera", str(e))
            return

        time.sleep(2.0)

        # Start OBS quietly
        if os.path.exists(OBS_EXE):
            self.clean_obs_safemode()
            cmd_obs = [
                OBS_EXE,
                "--startvirtualcam",
                "--minimize-to-tray"
            ]
            try:
                self.obs_proc = subprocess.Popen(
                    cmd_obs,
                    cwd=OBS_DIR,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception as e:
                print("OBS startup error:", e)

        self.is_running = True
        self.update_tray(True)
        rec_msg = " (Gravando MP4)" if self.is_recording else ""
        self.notify("Webcam Conectada", f"{self.device_name} ativo via USB{rec_msg}.")

    def stop_camera(self):
        if not self.is_running:
            return

        if self.scrcpy_proc:
            try:
                self.scrcpy_proc.terminate()
                self.scrcpy_proc.wait(timeout=2)
            except Exception:
                try:
                    self.scrcpy_proc.kill()
                except Exception:
                    pass
            self.scrcpy_proc = None

        if self.obs_proc:
            try:
                self.obs_proc.terminate()
                self.obs_proc.wait(timeout=2)
            except Exception:
                try:
                    self.obs_proc.kill()
                except Exception:
                    pass
            self.obs_proc = None

        subprocess.run(["taskkill", "/F", "/IM", "scrcpy.exe"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        subprocess.run(["taskkill", "/F", "/IM", "obs64.exe"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        self.clean_obs_safemode()

        self.is_running = False
        self.update_tray(False)

        if self.is_recording and self.current_record_file:
            self.notify("Gravação Salva", f"Arquivo salvo em:\n{os.path.basename(self.current_record_file)}")
            self.current_record_file = None

        self.notify("Webcam Desconectada", "Transmissão encerrada.")

    def restart_camera(self):
        if self.is_running:
            self.stop_camera()
            time.sleep(0.8)
            self.start_camera()

    def set_camera_id(self, cam_id):
        self.camera_id = cam_id
        self.notify("Lente Selecionada", f"Lente ID {cam_id} ativada.")
        if self.is_running:
            self.restart_camera()

    def set_zoom(self, zoom_val):
        self.zoom = zoom_val
        self.notify("Zoom", f"Nível de Zoom: {zoom_val}x")
        if self.is_running:
            self.restart_camera()

    def cycle_zoom(self):
        levels = ["1.0", "1.5", "2.0", "3.0"]
        try:
            curr = levels.index(self.zoom)
            nxt = (curr + 1) % len(levels)
        except ValueError:
            nxt = 0
        self.set_zoom(levels[nxt])

    def toggle_mirror(self):
        self.is_mirrored = not self.is_mirrored
        status = "Ativado (Natural)" if self.is_mirrored else "Desativado (Normal)"
        self.notify("Modo Espelho", f"Espelhamento horizontal: {status}")
        if self.is_running:
            self.restart_camera()

    def toggle_desk_view(self):
        self.is_desk_view = not self.is_desk_view
        status = "Ativado (180° Invertido)" if self.is_desk_view else "Desativado"
        self.notify("Modo Mesa / Documentos", f"Modo Mesa: {status}")
        if self.is_running:
            self.restart_camera()

    def toggle_mic(self):
        self.use_mic = not self.use_mic
        status = "Ativado" if self.use_mic else "Desativado"
        self.notify("Microfone USB", f"Áudio via USB: {status}")
        if self.is_running:
            self.restart_camera()

    def toggle_torch(self):
        self.torch_on = not self.torch_on
        mode = "1" if self.torch_on else "0"
        if self.selected_device:
            subprocess.run(
                [self.device_mgr.adb_exe, "-s", self.selected_device, "shell", f"cmd media.camera set-torch-mode 0 {mode}"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        status = "Ligada" if self.torch_on else "Desligada"
        self.notify("Lanterna / Ring Light", f"Iluminação de apoio: {status}")

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        val = "1" if self.is_muted else "0"
        if self.selected_device:
            subprocess.run(
                [self.device_mgr.adb_exe, "-s", self.selected_device, "shell", f"cmd media.camera set-camera-mute {val}"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        status = "VÍDEO MUTADO (Privacidade)" if self.is_muted else "Vídeo Ativo"
        self.notify("Modo Privacidade", status)

    def toggle_recording(self):
        self.is_recording = not self.is_recording
        status = "Iniciada" if self.is_recording else "Encerrada"
        self.notify("Gravação Local MP4", f"Gravação em disco: {status}")
        if self.is_running:
            self.restart_camera()

    def set_resolution(self, res, fps="30"):
        self.resolution = res
        self.fps = fps
        self.notify("Resolução", f"Qualidade alterada para {res} ({fps} FPS)")
        if self.is_running:
            self.restart_camera()

    def notify(self, title, message):
        if self.tray_icon:
            try:
                self.tray_icon.notify(message, title)
            except Exception:
                pass

    def update_tray(self, active):
        if self.tray_icon and self.icon_on and self.icon_off:
            self.tray_icon.icon = self.icon_on if active else self.icon_off

    def start_hotkeys(self):
        if not keyboard:
            return
        hotkeys_map = {
            '<ctrl>+<alt>+1': lambda: self.set_camera_id("1"),
            '<ctrl>+<alt>+2': lambda: self.set_camera_id("0"),
            '<ctrl>+<alt>+3': lambda: self.set_camera_id("2"),
            '<ctrl>+<alt>+z': self.cycle_zoom,
            '<ctrl>+<alt>+m': self.toggle_mute,
            '<ctrl>+<alt>+f': self.toggle_mirror,
            '<ctrl>+<alt>+d': self.toggle_desk_view,
            '<ctrl>+<alt>+l': self.toggle_torch,
            '<ctrl>+<alt>+r': self.toggle_recording,
        }
        try:
            self.hotkeys_listener = keyboard.GlobalHotKeys(hotkeys_map)
            self.hotkeys_listener.start()
        except Exception as e:
            print("Hotkey listener error:", e)

    def build_camera_menu_items(self):
        items = []
        if not self.available_cameras:
            items.append(item("Nenhuma lente detectada", None, enabled=False))
        else:
            for c in self.available_cameras:
                cam_id = c['id']
                label = c['label']
                items.append(
                    item(label, lambda _, cid=cam_id: self.set_camera_id(cid), checked=lambda _, cid=cam_id: self.camera_id == cid)
                )
        return items

    def build_menu(self):
        self.refresh_devices_and_cameras()
        return Menu(
            item(f"📱 {self.device_name}", None, enabled=False),
            Menu.SEPARATOR,
            item("🟢 Iniciar Webcam", lambda: self.start_camera(), visible=lambda _: not self.is_running),
            item("🛑 Parar Webcam", lambda: self.stop_camera(), visible=lambda _: self.is_running),
            Menu.SEPARATOR,
            item("📷 Selecionar Lente", Menu(lambda: self.build_camera_menu_items())),
            item("🔍 Nível de Zoom [Ctrl+Alt+Z]", Menu(
                item("1.0x (Padrão)", lambda: self.set_zoom("1.0"), checked=lambda _: self.zoom == "1.0"),
                item("1.5x (Close Suave)", lambda: self.set_zoom("1.5"), checked=lambda _: self.zoom == "1.5"),
                item("2.0x (Foco em Detalhes)", lambda: self.set_zoom("2.0"), checked=lambda _: self.zoom == "2.0"),
                item("3.0x (Telefoto)", lambda: self.set_zoom("3.0"), checked=lambda _: self.zoom == "3.0")
            )),
            item("🪞 Modo Espelho (Flip Horizontal) [Ctrl+Alt+F]", lambda: self.toggle_mirror(), checked=lambda _: self.is_mirrored),
            item("📄 Modo Mesa / Documentos (180°) [Ctrl+Alt+D]", lambda: self.toggle_desk_view(), checked=lambda _: self.is_desk_view),
            item("🛑 Modo Privacidade (Mutar Vídeo) [Ctrl+Alt+M]", lambda: self.toggle_mute(), checked=lambda _: self.is_muted),
            Menu.SEPARATOR,
            item("🎙️ Microfone USB", lambda: self.toggle_mic(), checked=lambda _: self.use_mic),
            item("💡 Lanterna / Ring Light [Ctrl+Alt+L]", lambda: self.toggle_torch(), checked=lambda _: self.torch_on),
            item("⏺️ Gravação Local MP4 [Ctrl+Alt+R]", lambda: self.toggle_recording(), checked=lambda _: self.is_recording),
            Menu.SEPARATOR,
            item("📐 Resolução", Menu(
                item("720p (HD 30fps) - Recomendado", lambda: self.set_resolution("1280x720", "30"), checked=lambda _: self.resolution == "1280x720"),
                item("1080p (Full HD 30fps) - Alta Definição", lambda: self.set_resolution("1920x1080", "30"), checked=lambda _: self.resolution == "1920x1080")
            )),
            item("📁 Abrir Pasta de Gravações", lambda: os.startfile(RECORDINGS_DIR)),
            Menu.SEPARATOR,
            item("❌ Sair", lambda: self.quit())
        )

    def quit(self):
        self.stop_camera()
        if self.hotkeys_listener:
            try:
                self.hotkeys_listener.stop()
            except Exception:
                pass
        if self.tray_icon:
            self.tray_icon.stop()

    def run(self):
        def on_setup(icon):
            icon.visible = True
            self.start_hotkeys()

        self.tray_icon = pystray.Icon(
            "AndroidWebcamPro",
            self.icon_off,
            "Universal Android Webcam Pro",
            menu=self.build_menu()
        )
        self.tray_icon.run(on_setup)

if __name__ == "__main__":
    app = UniversalWebcamApp()
    app.run()
