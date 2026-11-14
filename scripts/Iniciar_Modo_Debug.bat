@echo off
chcp 65001 >nul
title Android Webcam Pro - Debug Console
cd /d "C:\GalaxyWebcam"

echo ===================================================
echo     ANDROID WEBCAM PRO - INICIALIZADOR DE DEBUG
echo ===================================================
echo.
echo Iniciando monitor de diagnostico em tempo real...
echo.

start "" "C:\Python313\python.exe" "C:\GalaxyWebcam\debug_console.py"

echo Monitor iniciado em janela dedicada!
timeout /t 2 >nul
exit
