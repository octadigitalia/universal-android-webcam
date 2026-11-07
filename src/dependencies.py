import os
import sys
import time
import subprocess
import ctypes
from ctypes import wintypes

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_drivers_dir():
    # If bundled in PyInstaller _MEIPASS
    if hasattr(sys, '_MEIPASS'):
        meipass_drivers = os.path.join(sys._MEIPASS, "drivers")
        if os.path.exists(meipass_drivers):
            return meipass_drivers
    base = get_base_dir()
    local_drivers = os.path.join(base, "drivers")
    if os.path.exists(local_drivers):
        return local_drivers
    # Fallback to C:\GalaxyWebcam\drivers if in dev
    dev_drivers = r"C:\GalaxyWebcam\drivers"
    if os.path.exists(dev_drivers):
        return dev_drivers
    return local_drivers

def is_vcam_registered():
    """Checks if DirectShow OBS Virtual Camera COM filter is registered."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            r"CLSID\{A3FCE0F5-3493-419F-958A-ABA1250EC20B}\InprocServer32",
            0,
            winreg.KEY_READ
        )
        val = winreg.QueryValue(key, "")
        winreg.CloseKey(key)
        return bool(val and os.path.exists(val))
    except Exception:
        return False

def register_vcam():
    """Silently registers the bundled obs-virtualcam-module64.dll filter."""
    if is_vcam_registered():
        return True
    
    drivers_dir = get_drivers_dir()
    dll_path = os.path.join(drivers_dir, "vcam", "obs-virtualcam-module64.dll")
    if not os.path.exists(dll_path):
        return False
        
    # Attempt quiet registration
    try:
        res = subprocess.run(["regsvr32.exe", "/s", dll_path], capture_output=True)
        if res.returncode == 0 and is_vcam_registered():
            return True
    except Exception:
        pass
        
    # If needs admin elevation
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "regsvr32.exe", f'/s "{dll_path}"', None, 0
        )
        time.sleep(1.0)
        return is_vcam_registered()
    except Exception:
        return False

def check_virtual_microphone():
    """Checks if VB-Audio Virtual Cable (or any virtual cable) is registered in Windows audio."""
    try:
        winmm = ctypes.windll.winmm
        class WAVEOUTCAPS(ctypes.Structure):
            _fields_ = [
                ('wMid', wintypes.WORD),
                ('wPid', wintypes.WORD),
                ('vDriverVersion', wintypes.DWORD),
                ('szPname', ctypes.c_char * 32),
                ('dwFormats', wintypes.DWORD),
                ('wChannels', wintypes.WORD),
                ('wReserved1', wintypes.WORD),
                ('dwSupport', wintypes.DWORD),
            ]
        for i in range(winmm.waveOutGetNumDevs()):
            caps = WAVEOUTCAPS()
            winmm.waveOutGetDevCapsA(i, ctypes.byref(caps), ctypes.sizeof(caps))
            name = caps.szPname.decode('latin1', errors='ignore')
            if 'cable' in name.lower() or 'vb-audio' in name.lower():
                return name
    except Exception:
        pass
    return None

def install_virtual_microphone(ask_first=True, parent_hwnd=None):
    """Installs bundled VB-CABLE driver using UAC elevation."""
    if check_virtual_microphone():
        return True

    drivers_dir = get_drivers_dir()
    setup_exe = os.path.join(drivers_dir, "vbcable", "VBCABLE_Setup_x64.exe")
    if not os.path.exists(setup_exe):
        return False

    if ask_first:
        MB_YESNO = 0x00000004
        MB_ICONQUESTION = 0x00000020
        IDYES = 6
        title = "Universal Android Webcam Pro - Microfone Virtual"
        msg = (
            "Para transmitir a sua voz pelo celular em reuniões (Google Meet, Zoom, Teams)\n"
            "sem causar eco ou microfonia nos alto-falantes do computador, é necessário\n"
            "habilitar o driver de Microfone Virtual (VB-CABLE).\n\n"
            "Deseja configurar o microfone agora automaticamente?"
        )
        res = ctypes.windll.user32.MessageBoxW(parent_hwnd, msg, title, MB_YESNO | MB_ICONQUESTION)
        if res != IDYES:
            return False

    # Execute with elevation: -i (install) -h (hide / silent)
    try:
        ctypes.windll.shell32.ShellExecuteW(
            parent_hwnd,
            "runas",
            setup_exe,
            "-i -h",
            os.path.dirname(setup_exe),
            1
        )
        # Wait up to 6 seconds for registration to complete
        for _ in range(12):
            time.sleep(0.5)
            if check_virtual_microphone():
                return True
    except Exception as e:
        print("Driver installation error:", e)

    return bool(check_virtual_microphone())

def ensure_dependencies(ask_audio=True):
    """Verifies all runtime dependencies and auto-provisions missing ones."""
    # 1. Virtual Camera DirectShow filter
    if not is_vcam_registered():
        register_vcam()

    # 2. Virtual Microphone Driver
    if not check_virtual_microphone() and ask_audio:
        install_virtual_microphone(ask_first=True)
