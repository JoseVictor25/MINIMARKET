"""
dev.py – Servidor de desarrollo con Recarga en Vivo (Live Reload / Watcher).

Permite trabajar en el código y ver los cambios inmediatamente. Cada vez que guardes
un archivo (Ctrl+S), el watcher detecta el cambio y reinicia la aplicación automáticamente
en menos de un segundo, sin necesidad de tocar la terminal ni volver a ejecutar 'python main.py'.

Uso:
    python dev.py                    # Inicia la app normal con auto-recarga
    python dev.py --rol admin        # Auto-login como Administrador + auto-recarga
    python dev.py --rol cajero       # Auto-login como Cajero + auto-recarga
    python dev.py preview.py cierre  # Previsualiza un componente específico con auto-recarga
"""
import os
import sys
import time
import subprocess
from pathlib import Path

# Extensiones de archivo a monitorear
WATCH_EXTENSIONS = {".py", ".qss", ".css"}

# Carpetas o nombres a ignorar durante el escaneo
IGNORE_DIRS = {
    ".git", "__pycache__", "venv", ".venv", "env",
    "build", "dist", ".gemini", "tickets", "scratch",
    ".tempmediaStorage", ".user_uploaded", "brain"
}

import shutil

MIRROR_PATHS = [
    Path(r"c:\Users\Jose\Desktop\MINIMARKET"),
    Path(r"c:\Users\Jose\Desktop\SISTEMA MINI\MINIMARKET\MINIMARKET"),
]

def _obtener_raices_monitoreadas(raiz: Path) -> list[Path]:
    raices = [raiz.resolve()]
    for m in MIRROR_PATHS:
        try:
            mr = m.resolve()
            if m.exists() and mr not in raices:
                raices.append(mr)
        except Exception:
            pass
    return raices


def obtener_archivos_monitoreados(raices: list[Path]) -> dict[str, float]:
    """Retorna un diccionario {ruta_archivo: mtime} de todos los archivos relevantes."""
    archivos = {}
    for r in raices:
        for ruta, dirs, files in os.walk(r):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            for f in files:
                p = Path(ruta) / f
                if p.suffix.lower() in WATCH_EXTENSIONS:
                    try:
                        archivos[str(p.resolve())] = p.stat().st_mtime
                    except (OSError, FileNotFoundError):
                        pass
    return archivos


def matar_proceso(proc: subprocess.Popen | None):
    """Termina limpiamente el proceso hijo y su árbol en Windows."""
    if proc is None:
        return
    try:
        if proc.poll() is None:
            # En Windows, taskkill /F /T asegura que no queden procesos huérfanos
            subprocess.call(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def main():
    raiz = Path(__file__).resolve().parent
    args_extra = sys.argv[1:]

    # Determinar qué script ejecutar
    if args_extra and args_extra[0].endswith(".py"):
        target_script = args_extra[0]
        cmd = [sys.executable, target_script] + args_extra[1:]
    else:
        target_script = "main.py"
        cmd = [sys.executable, str(raiz / "main.py")] + args_extra

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    raices = _obtener_raices_monitoreadas(raiz)

    print("=" * 65)
    print(" [*] MINI MARKET POS - MODO DESARROLLO (LIVE RELOAD)")
    print("=" * 65)
    print(f" [>] Ejecutando : {' '.join(cmd)}")
    print(f" [o] Vigila     : {len(raices)} carpetas sincronizadas en vivo")
    print(" [i] Consejo   : Guarda cualquier cambio (Ctrl+S) y la app se recargara.")
    print(" [!] Para salir : Presiona Ctrl+C en esta terminal.")
    print("=" * 65)
    print()

    # Estado inicial de archivos
    estado_archivos = obtener_archivos_monitoreados(raices)

    # Iniciar primer proceso
    proc = subprocess.Popen(cmd)

    try:
        while True:
            time.sleep(0.4)

            # Verificar si el usuario cerró la ventana voluntariamente
            if proc.poll() is not None:
                nuevo_estado = obtener_archivos_monitoreados(raices)
                hubo_cambio = any(m != estado_archivos.get(r) for r, m in nuevo_estado.items())
                if not hubo_cambio and proc.returncode == 0:
                    print("\n[INFO] La aplicación fue cerrada. Finalizando modo desarrollo.")
                    break

            # Escanear cambios en archivos
            nuevo_estado = obtener_archivos_monitoreados(raices)
            archivo_cambiado = None

            for ruta, mtime in nuevo_estado.items():
                if ruta not in estado_archivos:
                    archivo_cambiado = ruta
                    break
                elif mtime != estado_archivos[ruta]:
                    archivo_cambiado = ruta
                    break

            if not archivo_cambiado:
                for ruta in estado_archivos:
                    if ruta not in nuevo_estado:
                        archivo_cambiado = ruta
                        break

            if archivo_cambiado:
                cambiado_p = Path(archivo_cambiado).resolve()
                raiz_origen = None
                for r in raices:
                    try:
                        cambiado_p.relative_to(r)
                        raiz_origen = r
                        break
                    except ValueError:
                        pass

                if raiz_origen:
                    rel_path = cambiado_p.relative_to(raiz_origen)
                    for r in raices:
                        if r != raiz_origen:
                            dest = r / rel_path
                            try:
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(cambiado_p, dest)
                            except Exception:
                                pass
                    nombre_rel = str(rel_path)
                else:
                    nombre_rel = os.path.basename(archivo_cambiado)

                print(f"\n[RECARGA] Cambio detectado en: {nombre_rel}")
                print("[*] Sincronizando y reiniciando ventana...")

                matar_proceso(proc)
                time.sleep(0.15)

                estado_archivos = obtener_archivos_monitoreados(raices)
                proc = subprocess.Popen(cmd)

    except KeyboardInterrupt:
        print("\n\n[INFO] Deteniendo servidor de desarrollo...")
    finally:
        matar_proceso(proc)
        print("[OK] Proceso finalizado limpiamente.")


if __name__ == "__main__":
    main()
