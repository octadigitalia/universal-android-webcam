import os
import sys
import time
import subprocess
import threading

BASE_DIR = r"C:\GalaxyWebcam" if os.path.exists(r"C:\GalaxyWebcam") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
DEBUG_LOG = os.path.join(LOGS_DIR, "debug.log")
os.makedirs(LOGS_DIR, exist_ok=True)

# ANSI Colors for Windows console
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
WHITE = "\033[97m"
BG_RED = "\033[41m"
RESET = "\033[0m"

# Enable ANSI in Windows terminal
os.system("")

def print_header():
    os.system("cls")
    print(f"{BOLD}{CYAN}======================================================================{RESET}")
    print(f"{BOLD}{GREEN}       📡 ANDROID WEBCAM PRO — MONITOR DE DEBUGGING AVANÇADO          {RESET}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}")
    print(f"{DIM}Legenda:{RESET}")
    print(f" {CYAN}● [USER_ACTION]{RESET} Ações do usuário no menu da bandeja")
    print(f" {YELLOW}● [ORIENTATION]{RESET} Giro físico do giroscópio do celular")
    print(f" {GREEN}● [MEET_VCAM]  {RESET} Taxa de frames (FPS) entregues ao Google Meet")
    print(f" {MAGENTA}● [STREAM]     {RESET} Troca a quente de lente e resolução")
    print(f" {MAGENTA}● [CAMERA_HAL] {RESET} Liberação de sessão física do sensor Android")
    print(f" {RED}● [SCRCPY_ERROR]{RESET} Erros internos do motor scrcpy")
    print(f" {YELLOW}● [SCRCPY_WARN]{RESET} Avisos de quadros ou demuxer")
    print(f"{CYAN}----------------------------------------------------------------------{RESET}\n")

def colorize(line):
    s = line.strip()
    if "[SCRCPY_ERROR]" in s or "[ERROR]" in s or "[AUDIO_ERROR]" in s:
        return f"{BOLD}{BG_RED}{WHITE} {s} {RESET}"
    elif "[SCRCPY_WARN]" in s or "[WARNING]" in s:
        return f"{BOLD}{YELLOW}{s}{RESET}"
    elif "[AUDIO]" in s:
        return f"{BOLD}{GREEN}{s}{RESET}"
    elif "[SCRCPY]" in s:
        return f"{DIM}{CYAN}{s}{RESET}"
    elif "[USER_ACTION]" in s:
        return f"{BOLD}{CYAN}{s}{RESET}"
    elif "[ORIENTATION]" in s:
        return f"{BOLD}{YELLOW}{s}{RESET}"
    elif "[DECODER]" in s:
        return f"{GREEN}{s}{RESET}"
    elif "[MEET_VCAM]" in s:
        return f"{BOLD}{GREEN}{s}{RESET}"
    elif "[CAMERA_HAL]" in s:
        return f"{BOLD}{MAGENTA}{s}{RESET}"
    elif "[SWITCH]" in s or "[STREAM]" in s:
        return f"{MAGENTA}{s}{RESET}"
    elif "[PIPELINE]" in s:
        return f"{CYAN}{s}{RESET}"
    elif "[FORWARDER]" in s:
        return f"{DIM}{s}{RESET}"
    return s

def follow_log(filepath):
    print_header()
    print(f"{YELLOW}Aguardando eventos no log ({filepath})...{RESET}\n")
    
    # Ensure file exists
    if not os.path.exists(filepath):
        open(filepath, "w", encoding="utf-8").close()

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        for l in lines[-20:]:
            print(colorize(l))
            
        while True:
            line = f.readline()
            if line:
                print(colorize(line))
            else:
                time.sleep(0.1)

if __name__ == "__main__":
    try:
        follow_log(DEBUG_LOG)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Monitor de debug encerrado pelo usuário.{RESET}")
