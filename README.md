# 📱 Universal Android Webcam Pro

Transform **any Android smartphone** into an ultra-low latency, professional webcam for Windows via USB. Designed for **Google Meet, Zoom, Microsoft Teams, Discord, CapCut, OBS**, and browsers.

[English](#features) | [Português](#recursos-em-português)

---

## ⚡ Highlights

* **Zero Latency (~25-35 ms):** Direct USB transfer using Android hardware-accelerated H.264 video encoding (`MediaCodec`).
* **100% Device-Agnostic:** Auto-detects connected phone brand, model, and physical camera sensors (Front, Back 50MP, Ultra-Wide 0.6x, Telephoto).
* **System Tray Control:** Runs unobtrusively in the Windows notification area (near the clock).
* **Global Hotkeys:** Switch lenses, toggle zoom, flip mirror mode, or mute video without leaving your call.
* **Studio USB Microphone:** Route the smartphone's noise-cancelling dual microphones to PC over USB.
* **Hardware Fill Light:** Toggle the phone's LED flash as a ring light for low-light environments.
* **Lossless Local MP4 Recording:** Record high-bitrate video directly to your PC while in a call.

---

## ⌨️ Global Hotkeys

| Shortcut | Action | Description |
| :--- | :--- | :--- |
| `Ctrl + Alt + 1` | 🤳 **Front Camera** | Switches to the selfie camera. |
| `Ctrl + Alt + 2` | 📸 **Main Camera** | Switches to the primary high-resolution back camera. |
| `Ctrl + Alt + 3` | 🔭 **Ultra-Wide** | Switches to 0.6x wide lens (great for room capture). |
| `Ctrl + Alt + Z` | 🔍 **Cycle Zoom** | Cycles: `1.0x` ➔ `1.5x` ➔ `2.0x` ➔ `3.0x`. |
| `Ctrl + Alt + F` | 🪞 **Mirror Mode** | Toggles horizontal flip (natural mirror look). |
| `Ctrl + Alt + D` | 📄 **Desk View (180°)** | Inverts 180° for document/desk presentation. |
| `Ctrl + Alt + M` | 🛑 **Privacy Mode** | Instant hardware camera mute. |
| `Ctrl + Alt + L` | 💡 **Ring Light** | Toggles the phone's back LED flashlight. |
| `Ctrl + Alt + R` | ⏺️ **Local Record** | Starts / stops recording to `Videos\AndroidWebcam\`. |

---

## 🛠️ Architecture

```
[ Android Smartphone ] ──(USB Cable / ADB)──> [ scrcpy v5.0.1 ]
       │                                              │
Hardware Camera2 API                             Direct3D 11
  & MediaCodec                                        │
                                                      ▼
[ Meet / Zoom / Teams / Discord ] <── DirectShow <── [ OBS Virtual Camera ]
```

1. **Android Side:** Communicates with `android.hardware.camera2` via ADB (`scrcpy-server`) with zero installed apps on the phone.
2. **PC Side:** The tray app manages video feed initialization via Direct3D 11 hardware decoding.
3. **Virtual Camera:** Injects frames directly into the registered DirectShow driver (`OBS Virtual Camera`).

---

## 🚀 Quick Start

### Option A: Standalone Executable (Recommended)
1. Download the latest release `.zip` from [Releases](https://github.com/octadigitalia/universal-android-webcam/releases).
2. Extract the folder and run `AndroidWebcamPro.exe`.
3. Enable **USB Debugging** on your Android phone (Settings > Developer Options > USB Debugging).
4. Plug in your USB cable, click **"🟢 Iniciar Webcam"** in the tray, and select **"OBS Virtual Camera"** in your video app!

### Option B: Running from Source
```bash
git clone https://github.com/octadigitalia/universal-android-webcam.git
cd universal-android-webcam
pip install -r requirements.txt
python src/main.py
```

---

<br>

# 🇧🇷 Recursos em Português

Transforme **qualquer smartphone Android** em uma webcam profissional de altíssima definição e **zero delay** via cabo USB para Windows.

### Principais Diferenciais:
* **Detecção Automática:** Reconhece o modelo do aparelho e lista as câmeras físicas reais (Selfie, Traseira 50MP, Ultra-Wide 0.6x).
* **Áudio USB de Estúdio:** Aproveita o microfone de ponta do smartphone com cancelamento de ruído nativo.
* **Atalhos Globais:** Alterne câmeras, dê zoom ou mute o vídeo instantaneamente pelo teclado sem sair da chamada.
* **Modo Mesa / Documentos (180°):** Aponte o celular para a mesa e mostre anotações ou cadernos com orientação perfeita.
* **Gravação Local Full HD:** Salve uma cópia cristalina em `.mp4` direto no seu computador.

---

## 📜 License
This project is open-source under the [MIT License](LICENSE).
Built with ❤️ by [OctaDigital](https://github.com/octadigitalia).
