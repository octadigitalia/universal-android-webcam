# 📱 Universal Android Webcam Pro

Transform **any Android smartphone** into an ultra-low latency, studio-grade webcam and USB microphone for Windows. Designed for **Google Meet, Zoom, Microsoft Teams, Discord, OBS, CapCut**, and browsers.

100% Pure Software. **Zero OBS Studio dependency required to run.**

[🇧🇷 Guia Completo em Português](#-guia-em-português) | [English Documentation](#-english-documentation)

---

## ⚡ Highlights / Destaques

* **⚡ Ultra-Low Latency (~20-35 ms):** Direct USB communication using hardware-accelerated H.264 video decoding.
* **🚫 100% Standalone (Zero OBS Needed):** Uses an embedded DirectShow virtual camera module. You do **not** need OBS Studio open or installed.
* **🔄 Adaptive Auto-Rotation (9:16 & 16:9):** Detects when you turn your phone physically in real time.
  * **Phone upright (vertical):** Automatic 9:16 portrait view (`360x640`).
  * **Phone landscape (horizontal):** Automatic 16:9 widescreen view (`640x360`).
  * **Auto-Letterbox:** Video stream to Google Meet/Zoom stays locked at standard 1280x720, preventing stretching or aspect ratio skew.
* **🎙️ Smart Virtual Microphone (Zero Microfonia):** Transmits high-fidelity 48kHz audio from your phone directly to your calls **without playing through your PC speakers**, completely eliminating feedback and echo.
* **📸 Live Seamless Lens Switching:** Switch between Front (Selfie), Main Back (50MP), and Ultra-Wide (0.6x) with a decoupled 30 FPS consumer thread that **never freezes or disconnects in Google Meet**.
* **💡 Ring Light & Hardware Torch:** Use your phone's LED flash as a physical ring light, or maximum screen brightness when on the front camera.
* **🪞 Natural Mirror Flip & Desk View:** Horizontal mirror mode for natural eye contact, or 180° inversion for presenting documents and desk drawings.
* **🛡️ Privacy Mode:** Instant in-stream video blackout (`Ctrl + Alt + M`).
* **📦 All-in-One Portable Executable:** Missing dependencies (DirectShow filter and Virtual Microphone) are automatically provisioned on the fly with 1 click.

---

# 🇧🇷 Guia em Português

O **Universal Android Webcam Pro** transforma qualquer celular Android em uma webcam profissional e microfone de estúdio de altíssima definição, conectado diretamente pelo cabo USB ao Windows.

### 🌟 Por que ele é diferente de outros apps (DroidCam, Camo, Iriun)?
1. **Sem apps instalados no celular:** Você não precisa instalar nenhum APK na Play Store. O app se conecta diretamente à API nativa de câmeras do Android via ADB.
2. **Sem anúncios, sem assinaturas e sem marcas d'água:** 100% gratuito e open-source.
3. **Zero OBS aberto:** Funciona com software puro e leve na bandeja do Windows (ao lado do relógio).
4. **Troca de lente contínua:** Você pode alternar entre a câmera frontal, traseira e grande-angular (0.6x) no meio da reunião sem que a imagem trave no Google Meet.
5. **Orientação Inteligente:** Gire o celular de pé ou deitado e a imagem se ajusta instantaneamente sem ficar deitada ou esticada.

---

### 🚀 Como Usar (Passo a Passo)

#### 1. Ativar a Depuração USB no seu Celular (Apenas uma vez)
1. No seu smartphone Android, abra as **Configurações**.
2. Vá em **Sobre o telefone** > **Informações do software**.
3. Toque **7 vezes seguidas** em **Número de compilação** até aparecer a mensagem *"Você agora é um desenvolvedor"*.
4. Volte ao menu principal de Configurações, abra **Opções do desenvolvedor** e ative a chave **Depuração USB**.

#### 2. Conectar e Iniciar
1. Baixe o pacote mais recente na aba **[Releases](https://github.com/octadigitalia/universal-android-webcam/releases)** (`AndroidWebcamPro-vX.X.X-win64.zip`).
2. Extraia o arquivo zip e dê dois cliques em `AndroidWebcamPro.exe`.
3. Conecte o celular ao computador com o cabo USB (se o celular pedir autorização para depuração USB, toque em *"Permitir sempre"*).
4. O ícone da câmera aparecerá na **bandeja do sistema** (perto do relógio do Windows).
5. Clique com o botão direito no ícone e selecione **🟢 Iniciar Webcam**.

#### 3. Configurar no Google Meet, Zoom ou Microsoft Teams
Abra as configurações de áudio e vídeo da sua chamada:
* **Vídeo (Câmera):** Selecione **`OBS Virtual Camera`**.
* **Áudio (Microfone):** Selecione **`CABLE Output (VB-Audio Virtual Cable)`**.
  *(Se você ainda não tiver o driver de áudio virtual, o próprio aplicativo perguntará se deseja instalar automaticamente em 1 clique).*

---

### ⌨️ Atalhos de Teclado Globais

Você pode controlar a câmera a qualquer momento pelo teclado sem precisar sair da janela da reunião:

| Atalho | Ação | Descrição |
| :--- | :--- | :--- |
| `Ctrl + Alt + 1` | 🤳 **Câmera Frontal** | Alterna imediatamente para a lente de selfie. |
| `Ctrl + Alt + 2` | 📸 **Câmera Traseira** | Ativa a lente principal de alta definição (50MP). |
| `Ctrl + Alt + 3` | 🔭 **Ultra-Wide (0.6x)** | Lente grande-angular para capturar todo o ambiente. |
| `Ctrl + Alt + Z` | 🔍 **Níveis de Zoom** | Alterna o zoom digital: `1.0x` ➔ `1.5x` ➔ `2.0x` ➔ `3.0x`. |
| `Ctrl + Alt + O` | ↷ **Girar 90°** | Ajuste fino manual da rotação da imagem. |
| `Ctrl + Alt + F` | 🪞 **Modo Espelho** | Inversão horizontal natural (efeito espelho). |
| `Ctrl + Alt + D` | 📄 **Modo Mesa (180°)** | Inverte a imagem 180° para apontar o celular para a mesa e mostrar documentos. |
| `Ctrl + Alt + M` | 🛑 **Modo Privacidade** | Corta o sinal de vídeo para tela preta instantânea. |
| `Ctrl + Alt + A` | 🎙️ **Transmitir Áudio** | Liga ou desliga o microfone do smartphone na chamada. |
| `Ctrl + Alt + L` | 💡 **Lanterna / Ring Light** | Liga o flash LED traseiro ou o Ring Light de tela frontal. |
| `Ctrl + Alt + R` | ⏺️ **Gravação Local** | Inicia/para a gravação de um arquivo `.mp4` em disco. |

---

# 🌐 English Documentation

## 🛠️ Architecture

```
[ Android Smartphone ] ──(USB 3.0 / ADB)──> [ scrcpy MediaCodec Stream ]
       │                                                   │
Camera2 Hardware API                                Named Pipe (MKV)
& Dual Microphones                                         │
                                                           ▼
                                                  [ Decoupled FFmpeg ]
                                                           │
                      ┌────────────────────────────────────┴────────────────────────────────────┐
                      ▼                                                                         ▼
         [ 30 FPS Video Pipeline ]                                                 [ Studio Audio Pipeline ]
                      │                                                                         │
       Direct3D Letterboxed Scale (NV12)                                         48 kHz Opus Direct Route
                      │                                                                         │
                      ▼                                                                         ▼
           [ OBS Virtual Camera ]                                                     [ VB-CABLE Input ]
            (DirectShow Filter)                                                      (Virtual Audio Driver)
                      │                                                                         │
                      └─────────────────────────────┬───────────────────────────────────────────┘
                                                    ▼
                             [ Google Meet / Zoom / Teams / Discord ]
```

### 🧩 Why the Decoupled Architecture Matters
* **No Google Meet Freeze:** DirectShow video input pins in Chromium pause or drop if frames stall for >1 second. Our dedicated consumer thread continuously feeds frames at a rock-solid 30.0 FPS clock, repeating the last clean frame during physical lens switches (~0.3s) so Google Meet never flags a buffer timeout.
* **Acoustic Isolation:** Unlike standard scrcpy audio playback which outputs to default PC speakers, our pipeline isolates phone audio to an internal virtual audio sink (`CABLE Input`), producing zero sound on your notebook speakers while delivering crisp phone microphone capture to your meeting participants.

---

## 💻 Running from Source

If you want to modify or contribute to the project:

### Prerequisites
* Windows 10 or 11 (64-bit)
* Python 3.11+
* Git

```bash
# Clone the repository
git clone https://github.com/octadigitalia/universal-android-webcam.git
cd universal-android-webcam

# Install Python requirements
pip install -r requirements.txt

# Run the app
python src/main.py
```

### Building the Standalone Release Package
To build the standalone `.exe` and `.zip` distribution locally:
```bash
python scripts/build_exe.py
```
This automatically compiles `AndroidWebcamPro.exe` via PyInstaller, bundles the drivers and dependencies, and produces a complete `.zip` in `release/`.

---

## 🤖 Automated CI/CD (GitHub Actions)

Releases are automatically compiled and published through GitHub Actions workflows:
* Regular commits to `master` keep the repository clean and light.
* Pushing a semantic version tag (e.g. `v1.0.0`) automatically launches a Windows runner, downloads fresh binaries, compiles the application, and publishes the official GitHub Release with the zipped package ready for download.

---

## 📜 License

This project is open-source under the [MIT License](LICENSE).

Developed with ❤️ by **[OctaDigital](https://github.com/octadigitalia)**.
