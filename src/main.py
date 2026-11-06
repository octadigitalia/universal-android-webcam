import os
import sys
import time
import datetime
import subprocess
import threading
import re

# Determine base directory whether running from script or PyInstaller frozen bundle
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure logs don't fail when running without console
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
if sys.stdout is None:
    sys.stdout = open(os.path.join(LOGS_DIR, "app.log"), "a", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.path.join(LOGS_DIR, "error.log"), "a", encoding="utf-8")

from PIL import Image
import pystray
from pystray import MenuItem as item, Menu
import numpy as np
import pyvirtualcam

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

if not os.path.exists(ICON_OFF_PATH):
    ICON_OFF_PATH = os.path.join(BASE_DIR, "icon_off.png")
    ICON_ON_PATH = os.path.join(BASE_DIR, "icon_on.png")

CREATE_NO_WINDOW = 0x08000000

class UniversalWebcamApp:
    def __init__(self):
        self.device_mgr = DeviceManager(BASE_DIR)
        self.is_running = False
        self.scrcpy_proc = None
        self.ffmpeg_proc = None
        self.vcam = None

        self.stream_thread = None
        self.orient_thread = None
        self.stop_stream_event = threading.Event()
        self.last_frame = None
        self._black_frame = None

        # Device & Lens State
        self.selected_device = None  # serial
        self.device_name = "Android"
        self.available_cameras = []
        self.camera_id = "1"
        self.width = 1280
        self.height = 720
        self.resolution = "1280x720"
        self.fps = 30
        self.zoom = "1.0"

        self._init_black_frame()

        # Orientation & Adaptation
        self.auto_rotate = True    # Detects physical device rotation
        self.device_rotation = 0   # 0, 90, 180, 270 degrees
        self.manual_rotation = 0   # User offset (0, 90, 180, 270)
        self.is_mirrored = True
        self.is_desk_view = False
        self.torch_on = False
        self.is_muted = False
        self.is_recording = False
        self.current_record_file = None

        self.icon_off = Image.open(ICON_OFF_PATH) if os.path.exists(ICON_OFF_PATH) else None
        self.icon_on = Image.open(ICON_ON_PATH) if os.path.exists(ICON_ON_PATH) else None
        self.tray_icon = None
        self.hotkeys_listener = None
        self._switch_lock = threading.Lock()

    def _init_black_frame(self):
        y_plane = np.zeros((self.height, self.width), dtype=np.uint8)
        uv_plane = np.full((self.height // 2, self.width), 128, dtype=np.uint8)
        self._black_frame = np.vstack([y_plane, uv_plane])

    def refresh_devices_and_cameras(self, force=False):
        """Scans for connected devices and cameras."""
        devices = self.device_mgr.get_connected_devices()
        if devices:
            if not self.selected_device or not any(d['serial'] == self.selected_device for d in devices):
                self.selected_device = devices[0]['serial']
                self.device_name = devices[0]['name']
            self.available_cameras = self.device_mgr.get_device_cameras(self.selected_device, force_refresh=force)
            front_cams = [c for c in self.available_cameras if c.get('facing') == 'front']
            if front_cams and self.camera_id not in [c['id'] for c in self.available_cameras]:
                self.camera_id = front_cams[0]['id']
        else:
            self.selected_device = None
            self.device_name = "Nenhum celular conectado"
            self.available_cameras = []

    def is_current_camera_back(self):
        for c in self.available_cameras:
            if str(c.get('id')) == str(self.camera_id):
                return c.get('facing') == 'back'
        return str(self.camera_id) in ["0", "2"]

    def query_device_rotation(self):
        """Queries physical orientation directly from hardware sensors (Device Orientation)."""
        if not self.selected_device:
            return self.device_rotation

        # 1. Hardware sensor
        try:
            res = subprocess.run(
                [self.device_mgr.adb_exe, "-s", self.selected_device, "shell", "dumpsys sensorservice"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=1.5
            )
            m = re.findall(r"Device Orient[^\n]*last 50 events[^\n]*\n((?:[^\n]+\n){1,55})", res.stdout)
            if m:
                vals = re.findall(r"\(\s*ts=[^)]+\)\s*(-?\d+)\.\d+", m[0])
                for v_str in reversed(vals):
                    v = int(v_str)
                    if v >= 0:
                        rot_deg = (360 - (v * 90)) % 360 if v in [1, 3] else (v * 90) % 360
                        return rot_deg
        except Exception:
            pass

        # 2. WindowManager fallback
        try:
            res = subprocess.run(
                [self.device_mgr.adb_exe, "-s", self.selected_device, "shell", "dumpsys window | grep mCurrentRotation"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=1.0
            )
            m = re.search(r"mCurrentRotation=ROTATION_(\d+)", res.stdout)
            if m:
                rot_code = int(m.group(1))
                return (rot_code * 90) % 360
        except Exception:
            pass

        return self.device_rotation

    def get_effective_rotation(self):
        base = self.device_rotation if self.auto_rotate else 0
        rot = (base + self.manual_rotation) % 360
        if self.is_desk_view:
            rot = (rot + 180) % 360
        return rot

    def get_orientation_flag(self):
        rot = self.get_effective_rotation()
        return f"flip{rot}" if self.is_mirrored else str(rot)

    def update_torch_state(self):
        if not self.selected_device:
            return
        is_back = self.is_current_camera_back()
        try:
            if self.torch_on:
                if not is_back:
                    subprocess.run([self.device_mgr.adb_exe, "-s", self.selected_device, "shell", "input keyevent KEYCODE_WAKEUP"], capture_output=True, creationflags=CREATE_NO_WINDOW)
                    subprocess.run([self.device_mgr.adb_exe, "-s", self.selected_device, "shell", "settings put system screen_brightness_mode 0 && settings put system screen_brightness 255"], capture_output=True, creationflags=CREATE_NO_WINDOW)
            else:
                if not is_back:
                    subprocess.run([self.device_mgr.adb_exe, "-s", self.selected_device, "shell", "settings put system screen_brightness 80 && settings put system screen_brightness_mode 1"], capture_output=True, creationflags=CREATE_NO_WINDOW)
        except Exception:
            pass

    def _orientation_watcher(self):
        while self.is_running:
            time.sleep(1.0)
            if not self.auto_rotate or not self.is_running:
                continue
            new_rot = self.query_device_rotation()
            if new_rot != self.device_rotation:
                self.device_rotation = new_rot
                self.notify("Orientação Adaptada", f"Celular girado para {new_rot}° — imagem ajustada.")
                self.live_switch_stream()

    def build_scrcpy_command(self, pipe_name):
        orient_flag = self.get_orientation_flag()
        cmd = [
            self.device_mgr.scrcpy_exe,
            "--no-audio",              # Silences audio capture completely
            "--no-audio-playback",     # NEVER plays audio to laptop speakers (avoids microfonia)
            "--video-source=camera",
            f"--camera-id={str(self.camera_id)}",
            f"--camera-size={self.resolution}",
            f"--camera-fps={self.fps}",
            f"--capture-orientation={orient_flag}",
            "--window-title=AndroidCam",
            "--window-width=640",
            "--window-height=360",
            f"--record={pipe_name}",
            "--record-format=mkv"
        ]

        if self.selected_device:
            cmd.extend(["-s", self.selected_device])

        if self.zoom != "1.0":
            cmd.append(f"--camera-zoom={self.zoom}")

        if self.torch_on and self.is_current_camera_back():
            cmd.append("--camera-torch")

        return cmd

    def _read_exact(self, stream, n):
        buf = bytearray()
        while len(buf) < n and not self.stop_stream_event.is_set():
            try:
                chunk = stream.read(n - len(buf))
                if not chunk:
                    break
                buf.extend(chunk)
            except Exception:
                break
        return bytes(buf) if len(buf) == n else None

    def _start_pipeline_processes(self):
        import win32pipe
        import win32file

        pipe_name = rf"\\.\pipe\android_cam_pipe_{int(time.time() * 1000)}"
        pipe = win32pipe.CreateNamedPipe(
            pipe_name,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            1, 65536, 65536, 0, None
        )

        self.update_torch_state()
        cmd_scrcpy = self.build_scrcpy_command(pipe_name)
        self.scrcpy_proc = subprocess.Popen(
            cmd_scrcpy,
            cwd=os.path.dirname(self.device_mgr.scrcpy_exe),
            creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        try:
            win32pipe.ConnectNamedPipe(pipe, None)
        except Exception:
            try:
                if self.ffmpeg_proc and self.ffmpeg_proc.stdin:
                    try:
                        self.ffmpeg_proc.stdin.close()
                    except Exception:
                        pass
                win32file.CloseHandle(pipe)
            except Exception:
                pass
            return None, None, None

        cmd_ffmpeg = [
            self.device_mgr.ffmpeg_exe,
            "-loglevel", "quiet",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-f", "matroska",
            "-i", "pipe:0",
            "-f", "rawvideo",
            "-pix_fmt", "nv12",
            "pipe:1"
        ]
        self.ffmpeg_proc = subprocess.Popen(
            cmd_ffmpeg,
            cwd=BASE_DIR,
            creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        def pipe_forwarder():
            while not self.stop_stream_event.is_set():
                try:
                    hr, data = win32file.ReadFile(pipe, 4096)
                    if data and self.ffmpeg_proc and self.ffmpeg_proc.stdin:
                        self.ffmpeg_proc.stdin.write(data)
                        self.ffmpeg_proc.stdin.flush()
                    else:
                        break
                except Exception:
                    break
            try:
                if self.ffmpeg_proc and self.ffmpeg_proc.stdin:
                    try:
                        self.ffmpeg_proc.stdin.close()
                    except Exception:
                        pass
                win32file.CloseHandle(pipe)
            except Exception:
                pass

        t_pipe = threading.Thread(target=pipe_forwarder, daemon=True)
        t_pipe.start()

        return self.scrcpy_proc, self.ffmpeg_proc, t_pipe

    def _stream_loop(self):
        frame_size = self.width * self.height * 3 // 2
        if self.last_frame is None or self.last_frame.shape != (self.height * 3 // 2, self.width):
            self.last_frame = self._black_frame

        while self.is_running:
            self.stop_stream_event.clear()
            p_scrcpy, p_ffmpeg, t_pipe = self._start_pipeline_processes()

            if not p_ffmpeg or not p_ffmpeg.stdout:
                time.sleep(0.5)
                continue

            while not self.stop_stream_event.is_set() and self.is_running:
                if self.is_muted:
                    if self.vcam:
                        self.vcam.send(self._black_frame)
                    time.sleep(0.033)
                    continue

                raw = self._read_exact(p_ffmpeg.stdout, frame_size)
                if raw:
                    frame = np.frombuffer(raw, dtype=np.uint8).reshape((self.height * 3 // 2, self.width))
                    self.last_frame = frame
                    if self.vcam:
                        self.vcam.send(frame)
                else:
                    if self.vcam and self.last_frame is not None:
                        self.vcam.send(self.last_frame)
                    time.sleep(0.033)

            try:
                if p_scrcpy:
                    p_scrcpy.terminate()
                    p_scrcpy.wait(timeout=0.5)
            except Exception:
                pass
            try:
                if p_ffmpeg:
                    if p_ffmpeg.stdin:
                        try:
                            p_ffmpeg.stdin.close()
                        except Exception:
                            pass
                    p_ffmpeg.terminate()
                    p_ffmpeg.wait(timeout=0.5)
            except Exception:
                pass

    def start_camera(self):
        if self.is_running:
            return

        self.refresh_devices_and_cameras(force=True)
        if not self.selected_device:
            self.notify("Dispositivo não detectado", "Conecte o smartphone via USB e ative a Depuração USB.")
            return

        try:
            self.vcam = pyvirtualcam.Camera(
                width=self.width,
                height=self.height,
                fps=self.fps,
                fmt=pyvirtualcam.PixelFormat.NV12,
                backend='obs'
            )
        except Exception as e:
            self.notify("Erro na Câmera Virtual", f"Falha ao iniciar DirectShow: {e}")
            return

        self.is_running = True
        self.device_rotation = self.query_device_rotation()
        self.stop_stream_event.clear()

        self.orient_thread = threading.Thread(target=self._orientation_watcher, daemon=True)
        self.orient_thread.start()

        self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self.stream_thread.start()

        self.update_tray(True)
        self.notify("Android Webcam Pro Ativa", f"{self.device_name} conectado a {self.resolution} via USB. Sem áudio nos alto-falantes.")
        self.update_menu_state()

    def stop_camera(self):
        if not self.is_running:
            return

        self.is_running = False
        self.stop_stream_event.set()

        if self.scrcpy_proc:
            try:
                self.scrcpy_proc.terminate()
                self.scrcpy_proc.wait(timeout=0.5)
            except Exception:
                pass
            self.scrcpy_proc = None

        if self.ffmpeg_proc:
            try:
                self.ffmpeg_proc.terminate()
                self.ffmpeg_proc.wait(timeout=0.5)
            except Exception:
                pass
            self.ffmpeg_proc = None

        subprocess.run(["taskkill", "/F", "/IM", "scrcpy.exe"], capture_output=True, creationflags=CREATE_NO_WINDOW)
        subprocess.run(["taskkill", "/F", "/IM", "ffmpeg.exe"], capture_output=True, creationflags=CREATE_NO_WINDOW)

        if self.vcam:
            try:
                self.vcam.close()
            except Exception:
                pass
            self.vcam = None

        if self.torch_on:
            self.torch_on = False
            self.update_torch_state()

        self.update_tray(False)
        self.notify("Android Webcam Desconectada", "Transmissão encerrada.")
        self.update_menu_state()

    def live_switch_stream(self):
        if not self.is_running:
            return
        with self._switch_lock:
            self.stop_stream_event.set()

    def set_camera_id(self, cam_id):
        self.camera_id = str(cam_id)
        label = f"ID {cam_id}"
        for c in self.available_cameras:
            if str(c.get('id')) == str(cam_id):
                label = c.get('label')
                break
        self.notify("Lente Selecionada", label)
        self.live_switch_stream()
        self.update_menu_state()

    def set_zoom(self, zoom_val):
        self.zoom = str(zoom_val)
        self.notify("Zoom", f"Nível de Zoom: {zoom_val}x")
        self.live_switch_stream()
        self.update_menu_state()

    def cycle_zoom(self):
        zoom_levels = ["1.0", "1.5", "2.0", "3.0"]
        try:
            curr_idx = zoom_levels.index(self.zoom)
            next_idx = (curr_idx + 1) % len(zoom_levels)
        except ValueError:
            next_idx = 0
        self.set_zoom(zoom_levels[next_idx])

    def toggle_mirror(self):
        self.is_mirrored = not self.is_mirrored
        status = "Ativado (Natural)" if self.is_mirrored else "Desativado (Normal)"
        self.notify("Modo Espelho", f"Espelhamento horizontal: {status}")
        self.live_switch_stream()
        self.update_menu_state()

    def toggle_auto_rotate(self):
        self.auto_rotate = not self.auto_rotate
        status = "Ativado (Detectar Giro do Celular)" if self.auto_rotate else "Desativado (Fixo)"
        self.notify("Auto-Rotação", status)
        if self.auto_rotate:
            self.device_rotation = self.query_device_rotation()
        self.live_switch_stream()
        self.update_menu_state()

    def set_manual_rotation(self, deg):
        self.manual_rotation = deg
        self.auto_rotate = False
        self.notify("Orientação da Imagem", f"Ângulo fixado em {deg}°")
        self.live_switch_stream()
        self.update_menu_state()

    def rotate_90(self):
        self.manual_rotation = (self.manual_rotation + 90) % 360
        self.auto_rotate = False
        self.notify("Girar 90°", f"Orientação ajustada para {self.manual_rotation}°")
        self.live_switch_stream()
        self.update_menu_state()

    def toggle_desk_view(self):
        self.is_desk_view = not self.is_desk_view
        status = "Ativado (180° Invertido)" if self.is_desk_view else "Desativado"
        self.notify("Modo Mesa / Documentos", f"Modo Mesa: {status}")
        self.live_switch_stream()
        self.update_menu_state()

    def toggle_torch(self):
        self.torch_on = not self.torch_on
        is_back = self.is_current_camera_back()
        if self.torch_on:
            msg = "Lanterna LED Traseira Ligada" if is_back else "Ring Light Frontal Ligado (Brilho 100%)"
        else:
            msg = "Iluminação Desligada"
        self.notify("Iluminação / Ring Light", msg)
        self.update_torch_state()
        if is_back:
            self.live_switch_stream()
        self.update_menu_state()

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        status = "VÍDEO MUTADO (Tela Preta de Privacidade)" if self.is_muted else "Vídeo Reativado"
        self.notify("Modo Privacidade", status)
        self.update_menu_state()

    def toggle_recording(self):
        self.is_recording = not self.is_recording
        status = "Iniciada" if self.is_recording else "Encerrada"
        self.notify("Gravação Local MP4", f"Gravação em disco: {status}")
        self.live_switch_stream()
        self.update_menu_state()

    def set_resolution(self, res, fps=30):
        self.resolution = res
        w, h = map(int, res.split("x"))
        self.width = w
        self.height = h
        self.fps = fps
        self._init_black_frame()
        self.notify("Resolução", f"Qualidade alterada para {res} ({fps} FPS)")
        if self.is_running:
            self.stop_camera()
            self.start_camera()
        self.update_menu_state()

    def notify(self, title, message):
        if self.tray_icon:
            try:
                self.tray_icon.notify(message, title)
            except Exception:
                pass

    def update_tray(self, active):
        if self.tray_icon and self.icon_on and self.icon_off:
            self.tray_icon.icon = self.icon_on if active else self.icon_off

    def update_menu_state(self):
        if self.tray_icon:
            try:
                self.tray_icon.menu = self.build_menu()
            except Exception:
                pass

    def start_hotkeys(self):
        if not keyboard:
            return
        hotkeys_map = {
            '<ctrl>+<alt>+1': lambda: self.set_camera_id("1"),
            '<ctrl>+<alt>+2': lambda: self.set_camera_id("0"),
            '<ctrl>+<alt>+3': lambda: self.set_camera_id("2"),
            '<ctrl>+<alt>+z': self.cycle_zoom,
            '<ctrl>+<alt>+o': self.rotate_90,
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
        def on_cam(cid):
            return lambda icon, item: self.set_camera_id(cid)

        def is_cam(cid):
            return lambda item: str(self.camera_id) == str(cid)

        items = []
        if not self.available_cameras:
            items.append(item("Nenhuma lente detectada", None, enabled=False))
        else:
            for c in self.available_cameras:
                cam_id = str(c['id'])
                label = c['label']
                items.append(
                    item(label, on_cam(cam_id), checked=is_cam(cam_id), radio=True)
                )
        return items

    def build_menu(self):
        self.refresh_devices_and_cameras()

        def on_zoom(z):
            return lambda icon, item: self.set_zoom(z)

        def is_zoom(z):
            return lambda item: str(self.zoom) == str(z)

        def on_res(r, f):
            return lambda icon, item: self.set_resolution(r, f)

        def is_res(r):
            return lambda item: str(self.resolution) == str(r)

        def on_rot(deg):
            return lambda icon, item: self.set_manual_rotation(deg)

        def is_rot(deg):
            return lambda item: not self.auto_rotate and self.manual_rotation == deg

        return Menu(
            item(f"📱 {self.device_name}", None, enabled=False),
            Menu.SEPARATOR,
            item("🟢 Iniciar Webcam", lambda icon, it: self.start_camera(), visible=lambda it: not self.is_running),
            item("🛑 Parar Webcam", lambda icon, it: self.stop_camera(), visible=lambda it: self.is_running),
            Menu.SEPARATOR,
            item("📷 Selecionar Lente", Menu(lambda: self.build_camera_menu_items())),
            item("🔍 Nível de Zoom [Ctrl+Alt+Z]", Menu(
                item("1.0x (Padrão)", on_zoom("1.0"), checked=is_zoom("1.0"), radio=True),
                item("1.5x (Close Suave)", on_zoom("1.5"), checked=is_zoom("1.5"), radio=True),
                item("2.0x (Foco em Detalhes)", on_zoom("2.0"), checked=is_zoom("2.0"), radio=True),
                item("3.0x (Telefoto)", on_zoom("3.0"), checked=is_zoom("3.0"), radio=True)
            )),
            item("🔄 Orientação da Imagem", Menu(
                item("🔄 Auto-Adaptar (Detectar Giro do Celular)", lambda icon, it: self.toggle_auto_rotate(), checked=lambda it: self.auto_rotate),
                item("↷ Girar 90° [Ctrl+Alt+O]", lambda icon, it: self.rotate_90()),
                Menu.SEPARATOR,
                item("0° (Normal - Em pé)", on_rot(0), checked=is_rot(0), radio=True),
                item("90° (Deitado - Lateral Direita)", on_rot(90), checked=is_rot(90), radio=True),
                item("180° (Invertido - Cabo por cima)", on_rot(180), checked=is_rot(180), radio=True),
                item("270° (Deitado - Lateral Esquerda)", on_rot(270), checked=is_rot(270), radio=True)
            )),
            item("🪞 Modo Espelho (Flip Horizontal) [Ctrl+Alt+F]", lambda icon, it: self.toggle_mirror(), checked=lambda it: self.is_mirrored),
            item("📄 Modo Mesa / Documentos (180°) [Ctrl+Alt+D]", lambda icon, it: self.toggle_desk_view(), checked=lambda it: self.is_desk_view),
            item("🛑 Modo Privacidade (Mutar Vídeo) [Ctrl+Alt+M]", lambda icon, it: self.toggle_mute(), checked=lambda it: self.is_muted),
            Menu.SEPARATOR,
            item("💡 Lanterna / Ring Light [Ctrl+Alt+L]", lambda icon, it: self.toggle_torch(), checked=lambda it: self.torch_on),
            item("⏺️ Gravação Local MP4 [Ctrl+Alt+R]", lambda icon, it: self.toggle_recording(), checked=lambda it: self.is_recording),
            Menu.SEPARATOR,
            item("📐 Resolução", Menu(
                item("720p (HD 30fps) - Recomendado", on_res("1280x720", 30), checked=is_res("1280x720"), radio=True),
                item("1080p (Full HD 30fps) - Alta Definição", on_res("1920x1080", 30), checked=is_res("1920x1080"), radio=True)
            )),
            item("📁 Abrir Pasta de Gravações", lambda icon, it: os.startfile(RECORDINGS_DIR)),
            Menu.SEPARATOR,
            item("❌ Sair", lambda icon, it: self.quit())
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
