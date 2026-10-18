"""
preview.py – Visualizador y Banco de Pruebas de Componentes UI en Tiempo Real.

Permite ver y probar cualquier diálogo, pantalla o widget de forma aislada e instantánea
SIN tener que iniciar sesión, navegar por el sistema o realizar ventas previas.

Características:
  • Auto-recarga en vivo por defecto: cada vez que guardes (Ctrl+S) un archivo .py o .qss,
    la ventana de vista previa se actualiza automáticamente en menos de un segundo.
  • Modo interactivo si no se especifican argumentos: muestra un menú visual para elegir
    cualquier pantalla con un solo clic.

Uso rápido:
    python preview.py                 # Abre el lanzador visual de todas las pantallas
    python preview.py cierre          # Diálogo de Cierre de Caja y Arqueo
    python preview.py apertura        # Diálogo de Apertura de Caja
    python preview.py confirmar       # Modal de confirmación de cierre
    python preview.py cobro           # Modal de cobro rápido con ítems de prueba
    python preview.py pos             # Pantalla completa del Punto de Venta (POS)
    python preview.py reportes        # Pantalla de Reportes y Estadísticas
    python preview.py productos       # Catálogo de Productos
    python preview.py ventas          # Historial de Ventas
    python preview.py inventario      # Ajustes de Inventario
    python preview.py compras         # Compras / Proveedores
    python preview.py login           # Pantalla de Login
    python preview.py --no-watch pos  # Abre sin auto-recarga
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
from pathlib import Path
from decimal import Decimal

# ── Extensiones y directorios para monitoreo ──────────────────────────────────
WATCH_EXTENSIONS = {".py", ".qss", ".css"}
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


def _obtener_archivos(raices: list[Path]) -> dict[str, float]:
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


def _matar_proceso(proc: subprocess.Popen | None):
    if proc is None:
        return
    try:
        if proc.poll() is None:
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


def _ejecutar_con_supervisor():
    """Ejecuta este script en un subproceso supervisado con auto-recarga en caliente."""
    raiz = Path(__file__).resolve().parent
    env = dict(os.environ)
    env["PREVIEW_SUPERVISOR_ACTIVE"] = "1"

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Filtrar el flag --no-watch si estuviera presente
    cmd = [sys.executable, str(Path(__file__).resolve())] + [a for a in sys.argv[1:] if a != "--watch"]
    raices = _obtener_raices_monitoreadas(raiz)

    print("=" * 65)
    print(" [*] MINI MARKET POS - VISTA PREVIA CON RECARGA EN VIVO")
    print("=" * 65)
    print(f" [>] Vista     : {' '.join(sys.argv[1:]) if sys.argv[1:] else 'Menu Selector'}")
    print(f" [o] Vigila    : {len(raices)} carpetas sincronizadas en vivo")
    print(" [i] Consejo   : Guarda cualquier cambio (Ctrl+S) y la ventana se actualizara.")
    print(" [!] Para salir: Presiona Ctrl+C o cierra la ventana.")
    print("=" * 65)
    print()

    estado = _obtener_archivos(raices)
    proc = subprocess.Popen(cmd, env=env)

    try:
        while True:
            time.sleep(0.35)

            # Si el usuario cerró la ventana normalmente sin cambios pendientes
            if proc.poll() is not None:
                nuevo_estado = _obtener_archivos(raices)
                hubo_cambio = any(m != estado.get(r) for r, m in nuevo_estado.items())
                if not hubo_cambio:
                    break

            nuevo_estado = _obtener_archivos(raices)
            cambiado = None
            for r, m in nuevo_estado.items():
                if m != estado.get(r):
                    cambiado = r
                    break
            if not cambiado:
                for r in estado:
                    if r not in nuevo_estado:
                        cambiado = r
                        break

            if cambiado:
                cambiado_p = Path(cambiado).resolve()
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
                    # Sincronizar automáticamente a las demás carpetas
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
                    nombre_rel = os.path.basename(cambiado)

                print(f"\n[RECARGA] Cambio detectado en: {nombre_rel}")
                print("[*] Sincronizando y actualizando vista previa...")

                _matar_proceso(proc)
                time.sleep(0.12)
                estado = _obtener_archivos(raices)
                proc = subprocess.Popen(cmd, env=env)

    except KeyboardInterrupt:
        print("\n[INFO] Cerrando vista previa...")
    finally:
        _matar_proceso(proc)


# ═════════════════════════════════════════════════════════════════════════════
#  LANZADORES DE COMPONENTES
# ═════════════════════════════════════════════════════════════════════════════

def lanzar_cierre():
    from ui.caja_dialog import CierreCajaDialog
    from database import SessionLocal
    from models.caja import SesionCaja

    s = SessionLocal()
    try:
        ses = s.query(SesionCaja).order_by(SesionCaja.id.desc()).first()
        ses_id = ses.id if ses else 1
    finally:
        s.close()

    dlg = CierreCajaDialog(sesion_caja_id=ses_id)
    dlg.exec_()


def lanzar_apertura():
    from ui.caja_dialog import AperturaCajaDialog
    from database import SessionLocal
    from models.usuario import Usuario

    s = SessionLocal()
    try:
        user = s.query(Usuario).filter_by(rol="cajero").first() or s.query(Usuario).first()
        s.expunge(user)
    finally:
        s.close()

    dlg = AperturaCajaDialog(usuario_actual=user)
    dlg.exec_()


def lanzar_confirmar_cierre():
    from ui.caja_dialog import ConfirmarCierreDialog
    dlg = ConfirmarCierreDialog(
        sesion_id=3,
        cajero="Patrick",
        turno="Tarde",
        esperado=Decimal("580.00"),
        fisico=Decimal("580.00"),
        diferencia=Decimal("0.00"),
        estado_arqueo_txt="CUADRADO (Sin diferencia)",
    )
    dlg.exec_()


def lanzar_cobro():
    from ui.pos_widget import CobrarDialog
    from database import SessionLocal
    from models.usuario import Usuario
    from models.cliente import Cliente

    s = SessionLocal()
    try:
        user = s.query(Usuario).first()
        cli = s.query(Cliente).first()

        class MockItem:
            def __init__(self, prod_id, cod, desc, cant, precio, subtotal):
                self.producto_id = prod_id
                self.codigo = cod
                self.descripcion = desc
                self.cantidad = cant
                self.precio_unitario = precio
                self.subtotal = subtotal

        items = [
            MockItem(1, "777001", "Arroz Diana Extra 1kg", 2, Decimal("8.50"), Decimal("17.00")),
            MockItem(2, "777002", "Aceite Fino 900ml", 1, Decimal("14.00"), Decimal("14.00")),
            MockItem(3, "777003", "Azúcar Guabirá 1kg", 3, Decimal("5.50"), Decimal("16.50")),
        ]
        total = sum(i.subtotal for i in items)
        dlg = CobrarDialog(total, s, items, user, cli, sesion_caja_id=1)
        dlg.exec_()
    finally:
        s.close()


def _get_sample_user(rol: str = "admin"):
    from database import SessionLocal
    from models.usuario import Usuario
    s = SessionLocal()
    try:
        user = s.query(Usuario).filter_by(rol=rol).first() or s.query(Usuario).first()
        if user:
            s.expunge(user)
        return user
    finally:
        s.close()


def lanzar_pos():
    from PyQt5.QtWidgets import QMainWindow
    from ui.pos_widget import POSWidget

    user = _get_sample_user(rol="cajero")
    win = QMainWindow()
    win.setWindowTitle("Vista Previa – Punto de Venta (POS)")
    pos = POSWidget(user, parent=win)
    win.setCentralWidget(pos)
    win.resize(1150, 760)
    win.show()
    return win


def lanzar_reportes():
    from PyQt5.QtWidgets import QMainWindow
    from ui.reportes_widget import ReportesWidget

    user = _get_sample_user(rol="admin")
    win = QMainWindow()
    win.setWindowTitle("Vista Previa – Reportes y Estadísticas")
    widget = ReportesWidget(usuario=user, parent=win)
    win.setCentralWidget(widget)
    win.resize(1100, 750)
    win.show()
    return win


def lanzar_productos():
    from PyQt5.QtWidgets import QMainWindow
    from ui.productos_widget import ProductosWidget

    user = _get_sample_user(rol="admin")
    win = QMainWindow()
    win.setWindowTitle("Vista Previa – Catálogo de Productos")
    widget = ProductosWidget(usuario=user, parent=win)
    win.setCentralWidget(widget)
    win.resize(1050, 700)
    win.show()
    return win


def lanzar_ventas():
    from PyQt5.QtWidgets import QMainWindow
    from ui.ventas_widget import VentasWidget

    user = _get_sample_user(rol="admin")
    win = QMainWindow()
    win.setWindowTitle("Vista Previa – Historial de Ventas")
    widget = VentasWidget(usuario=user, parent=win)
    win.setCentralWidget(widget)
    win.resize(1050, 700)
    win.show()
    return win


def lanzar_inventario():
    from PyQt5.QtWidgets import QMainWindow
    from ui.inventario_widget import InventarioWidget

    user = _get_sample_user(rol="admin")
    win = QMainWindow()
    win.setWindowTitle("Vista Previa – Ajustes de Inventario")
    widget = InventarioWidget(usuario=user, parent=win)
    win.setCentralWidget(widget)
    win.resize(1050, 700)
    win.show()
    return win


def lanzar_compras():
    from PyQt5.QtWidgets import QMainWindow
    from ui.compras_widget import ComprasWidget

    user = _get_sample_user(rol="admin")
    win = QMainWindow()
    win.setWindowTitle("Vista Previa – Registro de Compras")
    widget = ComprasWidget(usuario=user, parent=win)
    win.setCentralWidget(widget)
    win.resize(1050, 700)
    win.show()
    return win


def lanzar_usuarios():
    from PyQt5.QtWidgets import QMainWindow
    from ui.usuarios_widget import UsuariosWidget

    user = _get_sample_user(rol="admin")
    win = QMainWindow()
    win.setWindowTitle("Vista Previa – Gestión de Usuarios")
    widget = UsuariosWidget(usuario_actual=user, parent=win)
    win.setCentralWidget(widget)
    win.resize(950, 600)
    win.show()
    return win


def lanzar_login():
    from ui.login_dialog import LoginDialog
    dlg = LoginDialog()
    dlg.exec_()


# ── Menú Selector Gráfico ─────────────────────────────────────────────────────

def lanzar_menu_selector():
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QGridLayout,
        QPushButton, QLabel, QFrame, QScrollArea
    )
    from PyQt5.QtCore import Qt
    from ui.styles import PALETTE

    win = QMainWindow()
    win.setWindowTitle("Mini Market POS – Selector de Vistas Previas")
    win.resize(750, 620)

    central = QWidget()
    win.setCentralWidget(central)
    root = QVBoxLayout(central)
    root.setContentsMargins(28, 24, 28, 24)
    root.setSpacing(18)

    # Cabecera
    header = QLabel("🎨 Selector de Vista Previa UI")
    header.setStyleSheet("font-size: 22px; font-weight: 700; color: #ffffff;")
    sub = QLabel("Haz clic en cualquier pantalla para abrirla de inmediato sin pasos previos.\nCada cambio que guardes en el código (Ctrl+S) la recargará automáticamente.")
    sub.setStyleSheet("font-size: 13px; color: #94a3b8; line-height: 1.4;")
    root.addWidget(header)
    root.addWidget(sub)

    # Grid de opciones
    grid_frame = QFrame()
    grid_frame.setStyleSheet("""
        QFrame {
            background-color: #1e2238;
            border-radius: 12px;
            border: 1px solid #2e3458;
            padding: 10px;
        }
    """)
    grid = QGridLayout(grid_frame)
    grid.setSpacing(14)

    botones = [
        ("🔴 Cierre de Caja y Arqueo", "cierre", "#ef4444"),
        ("🟢 Apertura de Caja", "apertura", "#22c55e"),
        ("⚠️ Confirmar Cierre (Modal)", "confirmar", "#f59e0b"),
        ("💳 Modal de Cobro", "cobro", "#6366f1"),
        ("🛒 Punto de Venta (POS)", "pos", "#3b82f6"),
        ("📊 Reportes y Estadísticas", "reportes", "#8b5cf6"),
        ("📦 Catálogo de Productos", "productos", "#06b6d4"),
        ("📋 Historial de Ventas", "ventas", "#10b981"),
        ("📥 Ajuste de Inventario", "inventario", "#ec4899"),
        ("🚚 Registro de Compras", "compras", "#14b8a6"),
        ("👥 Gestión de Usuarios", "usuarios", "#f97316"),
        ("🔐 Diálogo de Login", "login", "#a855f7"),
    ]

    r, c = 0, 0
    for texto, comando, color in botones:
        btn = QPushButton(texto)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #262b48;
                border: 1px solid #363d66;
                border-left: 5px solid {color};
                border-radius: 8px;
                color: #e2e8f0;
                font-size: 13px;
                font-weight: 600;
                padding: 14px 16px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: #313860;
                border-color: {color};
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background-color: #1e2238;
            }}
        """)
        # Conectar botón
        def make_handler(cmd):
            return lambda: ejecutar_vista(cmd)
        btn.clicked.connect(make_handler(comando))

        grid.addWidget(btn, r, c)
        c += 1
        if c > 1:
            c = 0
            r += 1

    root.addWidget(grid_frame)
    win.show()
    return win


VISTAS = {
    "cierre": lanzar_cierre,
    "apertura": lanzar_apertura,
    "confirmar": lanzar_confirmar_cierre,
    "cobro": lanzar_cobro,
    "pos": lanzar_pos,
    "reportes": lanzar_reportes,
    "productos": lanzar_productos,
    "ventas": lanzar_ventas,
    "inventario": lanzar_inventario,
    "compras": lanzar_compras,
    "usuarios": lanzar_usuarios,
    "login": lanzar_login,
}


_ventana_activa = None

def ejecutar_vista(nombre: str):
    global _ventana_activa
    fn = VISTAS.get(nombre.lower())
    if fn:
        res = fn()
        if res is not None:
            _ventana_activa = res
    else:
        print(f"Error: Vista '{nombre}' no encontrada. Disponibles: {', '.join(VISTAS.keys())}")


def main():
    # Si no se pasó --no-watch y no estamos aún en el subproceso supervisado, activar supervisor
    if "--no-watch" not in sys.argv and os.environ.get("PREVIEW_SUPERVISOR_ACTIVE") != "1":
        _ejecutar_con_supervisor()
        return

    # Ejecución dentro del proceso Qt
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QFont
    from database import init_db
    from ui.styles import STYLESHEET

    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("Mini Market POS – Vista Previa")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLESHEET)

    # Identificar argumento de vista
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    vista_solicitada = args[0] if args else None

    global _ventana_activa
    if vista_solicitada:
        ejecutar_vista(vista_solicitada)
    else:
        _ventana_activa = lanzar_menu_selector()

    app.exec_()


if __name__ == "__main__":
    main()
