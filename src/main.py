import os
import sys
import time
import datetime
import subprocess
import threading
import re

BASE_DIR = r"C:\GalaxyWebcam"

# Ensure stdout and stderr exist even under pythonw.exe
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
import dependencies

try:
    from pynput import keyboard
except ImportError:
    keyboard = None

# Paths & Binaries
SCRCPY_DIR = os.path.join(BASE_DIR, "scrcpy-win64-v5.0.1")
SCRCPY_EXE = os.path.join(SCRCPY_DIR, "scrcpy.exe")
ADB_EXE = os.path.join(SCRCPY_DIR, "adb.exe")
FFMPEG_EXE = os.path.join(BASE_DIR, "ffmpeg.exe")

RECORDINGS_DIR = os.path.join(os.path.expanduser("~"), "Videos", "GalaxyWebcam")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

ICON_OFF_PATH = os.path.join(BASE_DIR, "icon_off.png")
ICON_ON_PATH = os.path.join(BASE_DIR, "icon_on.png")

CREATE_NO_WINDOW = 0x08000000

DEBUG_LOG_PATH = os.path.join(LOGS_DIR, "debug.log")

def write_debug_log(tag, msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"[{ts}] [{tag}] {msg}\n"
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
    except Exception:
        pass
    if sys.stdout:
        try:
            sys.stdout.write(line)
            sys.stdout.flush()
        except Exception:
            pass

class GalaxyWebcamApp:
    def __init__(self):
        self.is_running = False
        self.scrcpy_proc = None
        self.ffmpeg_proc = None
        self.vcam = None
        
        self.producer_thread = None
        self.consumer_thread = None
        self.orient_thread = None
        self.stop_stream_event = threading.Event()
        
        self.current_frame = None
        self._black_frame = None
        self._frame_lock = threading.Lock()
        
        # Camera Settings
        self.camera_id = "1"       # 1: Frontal, 0: Traseira Principal, 2: Ultra-Wide, 3: Frontal Secundária
        self.width = 1280
        self.height = 720
        self.resolution = "1280x720"
        self.fps = 30
        self.zoom = "1.0"          # 1.0, 1.5, 2.0, 3.0
        
        self._init_black_frame()

        # Orientation & Adaptation
        self.auto_rotate = True    # Detecta giro físico do celular
        self.device_rotation = 90  # 90: Vertical (em pé), 0: Horizontal (deitado)
        self.manual_rotation = 0   # Offset manual (0, 90, 180, 270)
        self.is_mirrored = True    # Flip horizontal (efeito espelho natural)
        self.is_desk_view = False  # Modo Documentos/Mesa (inversão 180°)
        self.current_pipe_handle = None
        self.audio_proc = None
        self.last_frame_time = 0
        
        # Feature Toggles
        self.torch_on = False      # Lanterna LED física (traseira) ou Ring Light de tela (frontal)
        self.is_muted = False      # Modo Privacidade (Vídeo Preto)
        self.audio_forwarding = True # Transmite microfone do celular para reuniões
        self.vbcable_device = None
        self.is_recording = False  # Gravação local MP4
        self.current_record_file = None

        # Auto-provision system drivers & dependencies on startup
        try:
            dependencies.ensure_dependencies(ask_audio=False)
            self.vbcable_device = dependencies.check_virtual_microphone()
        except Exception:
            pass

        self.icon_off = Image.open(ICON_OFF_PATH) if os.path.exists(ICON_OFF_PATH) else None
        self.icon_on = Image.open(ICON_ON_PATH) if os.path.exists(ICON_ON_PATH) else None
        self.tray_icon = None
        self.hotkeys_listener = None
        
        self._switch_lock = threading.Lock()

    def _init_black_frame(self):
        y_plane = np.zeros((self.height, self.width), dtype=np.uint8)
        uv_plane = np.full((self.height // 2, self.width), 128, dtype=np.uint8)
        self._black_frame = np.vstack([y_plane, uv_plane])

    def is_device_connected(self):
        try:
            res = subprocess.run(
                [ADB_EXE, "devices"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=6.0
            )
            for line in res.stdout.strip().splitlines():
                if "\tdevice" in line:
                    return True
            return False
        except Exception:
            return False

    def query_device_rotation(self):
        """Queries physical orientation directly from hardware sensors (Device Orientation)."""
        # 1. Query hardware sensor directly from Android sensorhub
        try:
            res = subprocess.run(
                [ADB_EXE, "shell", "dumpsys sensorservice"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=1.5
            )
            # Find strictly the Device Orientation event section up to the next unindented block
            section = re.search(r"Device Orient[^\n]*last 50 events.*?\n(.*?)(?:\n\S|\Z)", res.stdout, re.DOTALL)
            if section:
                lines = section.group(1).strip().splitlines()
                for l in reversed(lines):
                    m = re.search(r"\(\s*ts=[^)]+\)\s*(-?\d+)\.\d+", l)
                    if m:
                        v = int(m.group(1))
                        if v >= 0:
                            # Hardware sensor v:
                            # v=0: Celular em pé (Vertical) -> 90° (janela 9x16 vertical)
                            # v=1: Celular deitado -> 0° (janela 16x9 horizontal)
                            # v=2: Celular de ponta-cabeça -> 270° (9x16 vertical invertido)
                            # v=3: Celular deitado invertido -> 180° (16x9 horizontal)
                            rot_deg = (v * 270 + 90) % 360
                            return rot_deg
        except Exception:
            pass

        # 2. WindowManager fallback
        try:
            res = subprocess.run(
                [ADB_EXE, "shell", "dumpsys window | grep mCurrentRotation"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=1.0
            )
            m = re.search(r"mCurrentRotation=ROTATION_(\d+)", res.stdout)
            if m:
                rot_code = int(m.group(1))
                return (rot_code * 270 + 90) % 360
        except Exception:
            pass

        return self.device_rotation

    def get_effective_rotation(self):
        """Computes effective rotation angle in degrees."""
        if self.auto_rotate:
            rot = self.device_rotation
        else:
            rot = self.manual_rotation
        if self.is_desk_view:
            rot = (rot + 180) % 360
        return rot % 360

    def get_orientation_flag(self):
        rot = self.get_effective_rotation()
        is_front = str(self.camera_id) in ["1", "3"]
        if self.is_mirrored and is_front:
            # scrcpy applies 'flip' (horizontal sensor axis) BEFORE clockwise rotation rot.
            # To achieve correct screen horizontal mirroring without inverting vertically:
            # - rot=0°:   flip0
            # - rot=90°:  flip270 (prevents upside-down inversion!)
            # - rot=180°: flip180
            # - rot=270°: flip90  (prevents upside-down inversion!)
            mirror_map = {0: "flip0", 90: "flip270", 180: "flip180", 270: "flip90"}
            flag = mirror_map.get(rot, f"flip{rot}")
        else:
            flag = str(rot)
        return flag

    def update_torch_state(self):
        """Applies hardware torch (back LED) or virtual ring light (front screen brightness)."""
        is_back = str(self.camera_id) in ["0", "2"]
        try:
            if self.torch_on:
                if not is_back:
                    # Front camera: Virtual Ring Light via screen brightness
                    subprocess.run([ADB_EXE, "shell", "input keyevent KEYCODE_WAKEUP"], capture_output=True, creationflags=CREATE_NO_WINDOW)
                    subprocess.run([ADB_EXE, "shell", "settings put system screen_brightness_mode 0 && settings put system screen_brightness 255"], capture_output=True, creationflags=CREATE_NO_WINDOW)
            else:
                if not is_back:
                    subprocess.run([ADB_EXE, "shell", "settings put system screen_brightness 80 && settings put system screen_brightness_mode 1"], capture_output=True, creationflags=CREATE_NO_WINDOW)
        except Exception:
            pass

    def _orientation_watcher(self):
        """Background thread to detect when the phone is physically turned in real time."""
        last_candidate = None
        candidate_count = 0

        while self.is_running:
            time.sleep(0.5)
            if not self.auto_rotate or not self.is_running:
                last_candidate = None
                candidate_count = 0
                continue
            current_sensor_rot = self.query_device_rotation()
            if current_sensor_rot != self.device_rotation:
                if current_sensor_rot == last_candidate:
                    candidate_count += 1
                else:
                    last_candidate = current_sensor_rot
                    candidate_count = 1

                if candidate_count >= 2:
                    old_rot = self.device_rotation
                    self.device_rotation = current_sensor_rot
                    candidate_count = 0
                    last_candidate = None
                    write_debug_log("ORIENTATION", f"Sensor detected rotation change: {old_rot}° -> {current_sensor_rot}° (stable)")
                    self.notify("Orientação Adaptada", f"Celular girado para {current_sensor_rot}° — imagem ajustada.")
                    self.live_switch_stream()
            else:
                last_candidate = None
                candidate_count = 0

    def check_vbcable_device(self):
        return dependencies.check_virtual_microphone()

    def _start_audio_stream(self):
        """Streams phone microphone directly into VB-Audio Virtual Cable using DirectSound."""
        if not self.audio_forwarding:
            return
        if not self.check_vbcable_device():
            return
        if self.audio_proc and self.audio_proc.poll() is None:
            return

        env = os.environ.copy()
        env["SDL_AUDIODRIVER"] = "directsound"
        env["SDL_AUDIO_DEVICE_NAME"] = "CABLE Input (VB-Audio Virtual Cable)"

        cmd = [
            SCRCPY_EXE,
            "--port=27190",
            "--no-video",
            "--no-window",
            "--audio-source=mic"
        ]
        write_debug_log("AUDIO", "Starting dedicated phone microphone stream -> CABLE Input...")
        try:
            self.audio_proc = subprocess.Popen(
                cmd,
                cwd=SCRCPY_DIR,
                env=env,
                creationflags=CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            write_debug_log("AUDIO", f"Microphone forwarding active (PID {self.audio_proc.pid})")
        except Exception as e:
            write_debug_log("AUDIO_ERROR", f"Failed to start audio stream: {e}")

    def _stop_audio_stream(self):
        """Stops phone microphone stream cleanly."""
        if self.audio_proc:
            write_debug_log("AUDIO", "Stopping microphone stream...")
            try:
                self.audio_proc.kill()
            except Exception:
                pass
            self.audio_proc = None

    def build_scrcpy_command(self, pipe_name):
        orient_flag = self.get_orientation_flag()
        effective_rot = self.get_effective_rotation()
        is_vertical = effective_rot in [90, 270]
        win_w, win_h = (360, 640) if is_vertical else (640, 360)

        cmd = [
            SCRCPY_EXE,
            "--port=27183",
            "--video-source=camera",
            f"--camera-id={str(self.camera_id)}",
            f"--camera-size={self.resolution}",
            f"--camera-fps={self.fps}",
            f"--capture-orientation={orient_flag}",
            "--window-title=GalaxyCam",
            f"--window-width={win_w}",
            f"--window-height={win_h}",
            f"--record={pipe_name}",
            "--record-format=mkv",
            "--no-audio",  # CRITICAL: video-only stream prevents muxer overflow in named pipe!
            "--no-audio-playback"
        ]

        # Zoom level
        if self.zoom != "1.0":
            cmd.append(f"--camera-zoom={self.zoom}")

        # Hardware Torch (available on back cameras 0 and 2)
        if self.torch_on and str(self.camera_id) in ["0", "2"]:
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
        """Creates Named Pipe, launches scrcpy and ffmpeg, and connects the stream."""
        import win32pipe
        import win32file

        pipe_name = rf"\\.\pipe\galaxy_cam_pipe_{int(time.time() * 1000)}"
        pipe = win32pipe.CreateNamedPipe(
            pipe_name,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            1, 4 * 1024 * 1024, 4 * 1024 * 1024, 0, None
        )
        self.current_pipe_handle = pipe

        self.update_torch_state()
        cmd_scrcpy = self.build_scrcpy_command(pipe_name)
        scrcpy_env = os.environ.copy()

        self.scrcpy_proc = subprocess.Popen(
            cmd_scrcpy,
            cwd=SCRCPY_DIR,
            env=scrcpy_env,
            creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )

        def scrcpy_log_reader(proc):
            scrcpy_log_path = os.path.join(LOGS_DIR, "scrcpy.log")
            try:
                for line in iter(proc.stdout.readline, b''):
                    if not line:
                        break
                    text = line.decode('utf-8', errors='ignore').strip()
                    if not text:
                        continue
                    try:
                        with open(scrcpy_log_path, "a", encoding="utf-8") as f:
                            f.write(text + "\n")
                    except Exception:
                        pass
                    if "ERROR" in text or "error" in text:
                        write_debug_log("SCRCPY_ERROR", text)
                    elif "WARN" in text or "warn" in text:
                        write_debug_log("SCRCPY_WARN", text)
                    elif any(k in text for k in ["Using camera", "Device:", "Texture"]):
                        write_debug_log("SCRCPY", text)
            except Exception:
                pass

        t_scrcpy_log = threading.Thread(target=scrcpy_log_reader, args=(self.scrcpy_proc,), daemon=True)
        t_scrcpy_log.start()

        # Threaded pipe connect to never block indefinitely if scrcpy fails to start
        connected = [False]
        def connect_worker():
            import winerror
            try:
                win32pipe.ConnectNamedPipe(pipe, None)
                connected[0] = True
            except Exception as e:
                if getattr(e, 'winerror', None) == winerror.ERROR_PIPE_CONNECTED:
                    connected[0] = True

        t_conn = threading.Thread(target=connect_worker, daemon=True)
        t_conn.start()

        # Wait up to 12 seconds for scrcpy to connect on cold start
        for _ in range(120):
            if not t_conn.is_alive():
                break
            if self.scrcpy_proc and self.scrcpy_proc.poll() is not None:
                write_debug_log("SCRCPY_ERROR", f"scrcpy died prematurely with code {self.scrcpy_proc.poll()} before connecting to pipe")
                break
            if self.stop_stream_event.is_set():
                break
            time.sleep(0.1)

        if not connected[0]:
            # Unblock ConnectNamedPipe if it is waiting
            try:
                h = win32file.CreateFile(pipe_name, win32file.GENERIC_READ, 0, None, win32file.OPEN_EXISTING, 0, None)
                win32file.CloseHandle(h)
            except Exception:
                pass
            t_conn.join(timeout=0.5)
            try:
                win32file.CloseHandle(pipe)
            except Exception:
                pass
            self.current_pipe_handle = None
            if self.scrcpy_proc:
                try:
                    self.scrcpy_proc.terminate()
                except Exception:
                    pass
            return None, None, None

        cmd_ffmpeg = [
            FFMPEG_EXE,
            "-loglevel", "error",
            "-probesize", "32768",
            "-analyzeduration", "50000",
            "-flags", "low_delay",
            "-fflags", "discardcorrupt+nobuffer",
            "-threads", "1",
            "-f", "matroska",
            "-i", "pipe:0",
            "-an",
            "-r", str(self.fps),
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black",
            "-f", "rawvideo",
            "-pix_fmt", "nv12",
            "pipe:1"
        ]
        write_debug_log("PIPELINE", f"Spawning FFmpeg process (decoder)...")
        self.ffmpeg_proc = subprocess.Popen(
            cmd_ffmpeg,
            cwd=BASE_DIR,
            creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        def pipe_forwarder():
            write_debug_log("FORWARDER", "Pipe forwarder thread started.")
            total_fwd = 0
            while not self.stop_stream_event.is_set():
                try:
                    hr, data = win32file.ReadFile(pipe, 65536)
                    if data and self.ffmpeg_proc and self.ffmpeg_proc.stdin:
                        self.ffmpeg_proc.stdin.write(data)
                        self.ffmpeg_proc.stdin.flush()
                        total_fwd += len(data)
                    else:
                        break
                except Exception:
                    break
            write_debug_log("FORWARDER", f"Pipe forwarder stopped. Total bytes forwarded: {total_fwd}")

        t_pipe = threading.Thread(target=pipe_forwarder, daemon=True)
        t_pipe.start()

        return self.scrcpy_proc, self.ffmpeg_proc, t_pipe

    def _vcam_consumer_loop(self):
        """Dedicated DirectShow Virtual Camera clock thread (rock-solid 30 FPS)."""
        frame_interval = 1.0 / self.fps
        frames_sent = 0
        last_stat_time = time.time()

        while self.is_running:
            t0 = time.perf_counter()
            if self.vcam:
                if self.is_muted:
                    self.vcam.send(self._black_frame)
                    frames_sent += 1
                else:
                    with self._frame_lock:
                        frame_to_send = self.current_frame if self.current_frame is not None else self._black_frame
                    try:
                        self.vcam.send(frame_to_send)
                        frames_sent += 1
                    except Exception:
                        pass

            now = time.time()
            if now - last_stat_time >= 3.0:
                fps_rate = frames_sent / (now - last_stat_time)
                write_debug_log("MEET_VCAM", f"Transmitting to Google Meet at {fps_rate:.1f} FPS (low latency)")
                frames_sent = 0
                last_stat_time = now

            elapsed = time.perf_counter() - t0
            sleep_time = max(0.001, frame_interval - elapsed)
            time.sleep(sleep_time)

    def _stream_producer_loop(self):
        """Reads decoded frames from FFmpeg as fast as they arrive and updates self.current_frame."""
        frame_size = self.width * self.height * 3 // 2

        while self.is_running:
            self.stop_stream_event.clear()
            write_debug_log("STREAM", f"Starting stream: Cam ID {self.camera_id}, orient {self.get_orientation_flag()}")
            p_scrcpy, p_ffmpeg, t_pipe = self._start_pipeline_processes()

            if not p_ffmpeg or not p_ffmpeg.stdout:
                write_debug_log("STREAM", "Pipeline failed to initialize, retrying in 0.5s...")
                time.sleep(0.5)
                continue

            frames_decoded = 0
            last_stat_time = time.time()
            write_debug_log("STREAM", "Decoding loop entered. Reading frames from FFmpeg...")

            while not self.stop_stream_event.is_set() and self.is_running:
                raw = self._read_exact(p_ffmpeg.stdout, frame_size)
                if raw:
                    frame = np.frombuffer(raw, dtype=np.uint8).reshape((self.height * 3 // 2, self.width))
                    with self._frame_lock:
                        self.current_frame = frame
                        self.last_frame_time = time.time()
                    frames_decoded += 1

                    now = time.time()
                    if now - last_stat_time >= 3.0:
                        fps_rate = frames_decoded / (now - last_stat_time)
                        write_debug_log("DECODER", f"Decoded {frames_decoded} frames ({fps_rate:.1f} FPS)")
                        frames_decoded = 0
                        last_stat_time = now
                else:
                    # If read yielded None, check if child processes died
                    if (p_scrcpy and p_scrcpy.poll() is not None) or (p_ffmpeg and p_ffmpeg.poll() is not None):
                        write_debug_log("STREAM", f"Child process died (scrcpy: {p_scrcpy.poll() if p_scrcpy else None}, ffmpeg: {p_ffmpeg.poll() if p_ffmpeg else None})")
                        break
                    time.sleep(0.005)

            # Cleanup current segment cleanly
            write_debug_log("STREAM", "Cleaning up current stream segment...")
            try:
                if p_ffmpeg and p_ffmpeg.poll() is None:
                    p_ffmpeg.kill()
                    p_ffmpeg.wait(timeout=0.2)
            except Exception:
                pass

            try:
                if p_ffmpeg and p_ffmpeg.stdin:
                    p_ffmpeg.stdin.close()
            except Exception:
                pass

            try:
                if p_scrcpy and p_scrcpy.poll() is None:
                    p_scrcpy.kill()
                    p_scrcpy.wait(timeout=0.2)
            except Exception:
                pass

            if self.current_pipe_handle:
                try:
                    win32file.CloseHandle(self.current_pipe_handle)
                except Exception:
                    pass
                self.current_pipe_handle = None

            if t_pipe and t_pipe.is_alive():
                t_pipe.join(timeout=0.2)

            # Cooldown to ensure Android CameraService HAL completes release of exclusive camera session
            write_debug_log("CAMERA_HAL", f"Released Camera ID {self.camera_id}. Cooldown 400ms...")
            time.sleep(0.4)

    def start_camera(self):
        """Starts 100% pure standalone webcam and preview window (ZERO OBS)."""
        if self.is_running:
            return

        if not self.is_device_connected():
            self.notify("Galaxy S24 FE não detectado", "Verifique o cabo USB e a Depuração USB.")
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

        # 1. Start dedicated Consumer thread (keeps Google Meet feed 100% continuous and awake)
        self.consumer_thread = threading.Thread(target=self._vcam_consumer_loop, daemon=True)
        self.consumer_thread.start()

        # 2. Start Producer thread (fetches frames from scrcpy/ffmpeg)
        self.producer_thread = threading.Thread(target=self._stream_producer_loop, daemon=True)
        self.producer_thread.start()

        # 3. Start Orientation Watcher thread
        self.orient_thread = threading.Thread(target=self._orientation_watcher, daemon=True)
        self.orient_thread.start()

        # 4. Start dedicated phone microphone audio streaming to VB-CABLE
        if self.audio_forwarding:
            self._start_audio_stream()

        self.update_tray(True)
        self.notify("Galaxy Webcam Pro Ativa", f"Conectada a {self.resolution} via USB. Transmissão contínua para Google Meet.")
        self.update_menu_state()

        if self.audio_forwarding and not dependencies.check_virtual_microphone():
            threading.Thread(target=self._prompt_audio_setup, daemon=True).start()

    def _prompt_audio_setup(self):
        if dependencies.install_virtual_microphone(ask_first=True):
            self.vbcable_device = dependencies.check_virtual_microphone()
            self.notify("Microfone Virtual", "Driver configurado! Áudio pronto para Google Meet/Zoom.")
            self._start_audio_stream()
            self.update_menu_state()

    def stop_camera(self):
        """Stops the webcam stream and closes the virtual camera device."""
        if not self.is_running:
            return

        self.is_running = False
        self.stop_stream_event.set()
        self._stop_audio_stream()

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
        self.notify("Galaxy Webcam Desconectada", "Transmissão encerrada.")
        self.update_menu_state()

    def live_switch_stream(self):
        """Smoothly switches video feed without dropping the Virtual Camera in Google Meet."""
        if not self.is_running:
            return

        with self._switch_lock:
            write_debug_log("SWITCH", f"live_switch_stream requested (camera={self.camera_id}, orient={self.get_orientation_flag()}, zoom={self.zoom})")
            # Signal producer loop to restart scrcpy while consumer thread keeps streaming to Meet!
            self.stop_stream_event.set()
            # Proactively terminate current segment processes so read() and named pipe unblock instantly (0ms)
            if self.ffmpeg_proc:
                try:
                    self.ffmpeg_proc.kill()
                except Exception:
                    pass
            if self.scrcpy_proc:
                try:
                    self.scrcpy_proc.kill()
                except Exception:
                    pass

    def set_camera_id(self, cam_id):
        if str(self.camera_id) == str(cam_id):
            return
        write_debug_log("USER_ACTION", f"User selected Camera ID: {cam_id}")
        self.camera_id = str(cam_id)
        names = {
            "1": "Frontal (Selfie)",
            "0": "Traseira Principal (50 MP)",
            "2": "Ultra-Wide (0.6x)",
            "3": "Frontal Secundária"
        }
        self.notify("Lente Selecionada", names.get(str(cam_id), f"ID {cam_id}"))
        self.live_switch_stream()
        self.update_menu_state()

    def set_zoom(self, zoom_val):
        write_debug_log("USER_ACTION", f"User set Zoom: {zoom_val}x")
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
        write_debug_log("USER_ACTION", f"User toggled Mirror: {status}")
        self.notify("Modo Espelho", f"Espelhamento horizontal: {status}")
        self.live_switch_stream()
        self.update_menu_state()

    def toggle_auto_rotate(self):
        self.auto_rotate = not self.auto_rotate
        if self.auto_rotate:
            self.manual_rotation = 0  # Reset manual offset so auto-rotation is clean!
            self.device_rotation = self.query_device_rotation()
        status = "Ativado (Detectar Giro do Celular)" if self.auto_rotate else "Desativado (Fixo)"
        write_debug_log("USER_ACTION", f"User toggled Auto-Rotate: {status}")
        self.notify("Auto-Rotação", status)
        self.live_switch_stream()
        self.update_menu_state()

    def set_manual_rotation(self, deg):
        write_debug_log("USER_ACTION", f"User selected Manual Rotation: {deg}°")
        self.manual_rotation = deg
        self.auto_rotate = False
        self.notify("Orientação da Imagem", f"Ângulo fixado em {deg}°")
        self.live_switch_stream()
        self.update_menu_state()

    def rotate_90(self):
        """Rotates image 90 degrees clockwise."""
        base = self.device_rotation if self.auto_rotate else self.manual_rotation
        self.manual_rotation = (base + 90) % 360
        self.auto_rotate = False
        write_debug_log("USER_ACTION", f"User rotated 90° -> Manual {self.manual_rotation}°")
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
        is_back = str(self.camera_id) in ["0", "2"]
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
        """Instant in-stream video blackout for 100% privacy."""
        self.is_muted = not self.is_muted
        status = "VÍDEO MUTADO (Tela Preta de Privacidade)" if self.is_muted else "Vídeo Reativado"
        self.notify("Modo Privacidade", status)
        self.update_menu_state()

    def toggle_audio(self):
        self.audio_forwarding = not self.audio_forwarding
        status = "Ativada (Microfone Ativo)" if self.audio_forwarding else "Desativada"
        write_debug_log("USER_ACTION", f"User toggled Audio: {status}")
        self.notify("Transmissão de Áudio", f"Microfone do celular: {status}")
        if self.audio_forwarding and self.is_running:
            self._start_audio_stream()
        else:
            self._stop_audio_stream()
        self.update_menu_state()

    def launch_vbcable_installer(self):
        installed = dependencies.install_virtual_microphone(ask_first=False)
        if installed:
            self.vbcable_device = dependencies.check_virtual_microphone()
            self.notify("Microfone Virtual", "Driver instalado e ativado com sucesso!")
            self.live_switch_stream()
            self.update_menu_state()
        else:
            self.notify("Microfone Virtual", "Instalação cancelada ou pendente de permissão.")

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
        if self.tray_icon:
            self.tray_icon.icon = self.icon_on if active else self.icon_off

    def update_menu_state(self):
        """Forces pystray to rebuild its menu items so checkmarks update in real-time."""
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
            '<ctrl>+<alt>+a': self.toggle_audio,
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

    def build_menu(self):
        def on_cam(cid):
            return lambda icon, item: self.set_camera_id(cid)

        def is_cam(cid):
            return lambda item: str(self.camera_id) == str(cid)

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
            item("🟢 Iniciar Webcam", lambda icon, it: self.start_camera(), visible=lambda it: not self.is_running),
            item("🛑 Parar Webcam", lambda icon, it: self.stop_camera(), visible=lambda it: self.is_running),
            Menu.SEPARATOR,
            item("📷 Selecionar Lente", Menu(
                item("🤳 Frontal (Selfie) [Ctrl+Alt+1]", on_cam("1"), checked=is_cam("1"), radio=True),
                item("📸 Traseira Principal (50 MP) [Ctrl+Alt+2]", on_cam("0"), checked=is_cam("0"), radio=True),
                item("🔭 Ultra-Wide (0.6x) [Ctrl+Alt+3]", on_cam("2"), checked=is_cam("2"), radio=True),
                item("🤳 Frontal Secundária", on_cam("3"), checked=is_cam("3"), radio=True)
            )),
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
                item("90° (Vertical - Celular em pé)", on_rot(90), checked=is_rot(90), radio=True),
                item("0° (Horizontal - Celular deitado)", on_rot(0), checked=is_rot(0), radio=True),
                item("270° (Vertical Invertido)", on_rot(270), checked=is_rot(270), radio=True),
                item("180° (Horizontal Invertido)", on_rot(180), checked=is_rot(180), radio=True)
            )),
            item("🪞 Modo Espelho (Flip Horizontal) [Ctrl+Alt+F]", lambda icon, it: self.toggle_mirror(), checked=lambda it: self.is_mirrored),
            item("📄 Modo Mesa / Documentos (180°) [Ctrl+Alt+D]", lambda icon, it: self.toggle_desk_view(), checked=lambda it: self.is_desk_view),
            item("🛑 Modo Privacidade (Mutar Vídeo) [Ctrl+Alt+M]", lambda icon, it: self.toggle_mute(), checked=lambda it: self.is_muted),
            Menu.SEPARATOR,
            item("🎙️ Transmissão de Áudio (Microfone)", Menu(
                item("🎙️ Transmitir Microfone do Celular [Ctrl+Alt+A]", lambda icon, it: self.toggle_audio(), checked=lambda it: self.audio_forwarding),
                item("🛠️ Configurar Microfone Virtual (Auto)", lambda icon, it: self.launch_vbcable_installer())
            )),
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
            "GalaxyWebcam",
            self.icon_off,
            "Galaxy S24 FE Webcam Pro",
            menu=self.build_menu()
        )
        self.tray_icon.run(on_setup)

if __name__ == "__main__":
    try:
        app = GalaxyWebcamApp()
        app.run()
    except Exception as e:
        import traceback
        with open(r"C:\GalaxyWebcam\crash.txt", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
