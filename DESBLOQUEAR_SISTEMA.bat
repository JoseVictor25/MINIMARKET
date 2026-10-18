@echo off
title Desbloquear Mini Market para este equipo
color 0A
echo.
echo ============================================================
echo   DESBLOQUEANDO ARCHIVOS Y LIBRERIAS PARA WINDOWS
echo ============================================================
echo.
echo Desbloqueando directivas de seguridad locales en Windows...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%~dp0' -Recurse | Unblock-File"
echo.
echo ============================================================
echo   LISTO! Archivos desbloqueados exitosamente.
echo   Ya puedes abrir MiniMarket.exe sin problemas de directivas.
echo ============================================================
echo.
pause
