"""
ui/main_window.py – Ventana principal con barra lateral de navegación.
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget,
    QLabel, QPushButton, QStatusBar, QFrame,
    QMessageBox, QFileDialog, QDialog,
)
from PyQt5.QtGui import QFont, QIcon, QPixmap

from config import APP_NAME, APP_VERSION, DB_PATH
from models.usuario import Usuario
from services.ticket_service import respaldar_base_de_datos
from services.inventario_service import productos_con_stock_bajo
from database import SessionLocal
from ui.styles import PALETTE

# Widgets de cada sección
from ui.pos_widget       import POSWidget
from ui.caja_widget      import CajaWidget
from ui.productos_widget import ProductosWidget
from ui.compras_widget   import ComprasWidget
from ui.ventas_widget    import VentasWidget
from ui.reportes_widget  import ReportesWidget
from ui.inventario_widget import InventarioWidget
from ui.maestros_widget  import MaestrosWidget
from ui.usuarios_widget  import UsuariosWidget


# Definición de secciones separadas por Rol
SECCIONES_ADMIN = [
    ("📦  Productos",          "productos"),
    ("📊  Inventario",         "inventario"),
    ("🚚  Compras",            "compras"),
    ("📋  Ventas",             "ventas"),
    ("📈  Reportes",           "reportes"),
    ("💵  Control de Caja",    "caja"),
    ("🗂  Maestros",           "maestros"),
    ("👥  Usuarios",           "usuarios"),
    ("🛒  Punto de Venta",     "pos"),
]

SECCIONES_CAJERO = [
    ("🛒  Punto de Venta",     "pos"),
    ("💵  Mi Turno y Caja",    "caja"),
    ("📋  Mis Ventas",         "ventas"),
    ("📦  Consultar Stock",    "productos"),
]


class CerrarSesionDialog(QDialog):
    """Diálogo modal estilizado con diseño premium para confirmar el cierre de sesión."""

    def __init__(self, usuario: Usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Cerrar Sesión")
        self.setFixedWidth(460)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Cuerpo ────────────────────────────────────────────────────────────
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(28, 24, 28, 20)
        body_lay.setSpacing(16)

        # Encabezado con badge y títulos
        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        icon_badge = QLabel()
        icon_badge.setObjectName("logout_icon_badge")
        icon_badge.setFixedSize(54, 54)
        icon_badge.setAlignment(Qt.AlignCenter)
        pix = QPixmap("assets/logout_icon.png")
        if not pix.isNull():
            icon_badge.setPixmap(pix.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_badge.setStyleSheet("""
            #logout_icon_badge {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                    stop:0 rgba(239, 68, 68, 0.22), stop:1 rgba(239, 68, 68, 0.06));
                border: 2px solid rgba(239, 68, 68, 0.4);
                border-radius: 27px;
            }
        """)
        header_row.addWidget(icon_badge)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        lbl_title = QLabel("¿Cerrar Sesión?")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff; border: none;")
        lbl_sub = QLabel("¿Estás seguro de que deseas salir del sistema?")
        lbl_sub.setStyleSheet("font-size: 13px; color: #94a3b8; border: none;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header_row.addLayout(title_box)
        header_row.addStretch()

        body_lay.addLayout(header_row)

        # Tarjeta de perfil de usuario
        profile_card = QFrame()
        profile_card.setObjectName("profile_card")
        profile_card.setStyleSheet("""
            #profile_card {
                background-color: #1a2436;
                border: 1px solid #2e3e55;
                border-radius: 12px;
            }
        """)
        card_lay = QHBoxLayout(profile_card)
        card_lay.setContentsMargins(14, 12, 14, 12)
        card_lay.setSpacing(14)

        # Avatar circular con inicial
        inicial = (self.usuario.nombre_completo or self.usuario.username or "U")[0].upper()
        avatar = QLabel(inicial)
        avatar.setObjectName("avatar_lbl")
        avatar.setFixedSize(44, 44)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(f"""
            #avatar_lbl {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {PALETTE['accent']}, stop:1 {PALETTE['accent_dark']});
                color: #ffffff;
                font-size: 18px;
                font-weight: bold;
                border-radius: 22px;
                border: 2px solid rgba(255, 255, 255, 0.2);
            }}
        """)
        card_lay.addWidget(avatar)

        # Datos del usuario
        info_vbox = QVBoxLayout()
        info_vbox.setSpacing(3)

        lbl_nombre = QLabel(self.usuario.nombre_completo or self.usuario.username)
        lbl_nombre.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff; border: none;")
        info_vbox.addWidget(lbl_nombre)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)

        lbl_user = QLabel(f"@{self.usuario.username}")
        lbl_user.setStyleSheet("font-size: 12px; color: #94a3b8; border: none;")
        meta_row.addWidget(lbl_user)

        lbl_sep = QLabel("•")
        lbl_sep.setStyleSheet("color: #475569; font-size: 12px; border: none;")
        meta_row.addWidget(lbl_sep)

        lbl_rol = QLabel(self.usuario.rol_display)
        lbl_rol.setStyleSheet(f"""
            background: rgba(14, 165, 233, 0.15);
            color: {PALETTE['accent_hover']};
            border: 1px solid rgba(14, 165, 233, 0.3);
            border-radius: 4px;
            padding: 1px 8px;
            font-size: 11px;
            font-weight: bold;
        """)
        meta_row.addWidget(lbl_rol)
        meta_row.addStretch()

        info_vbox.addLayout(meta_row)
        card_lay.addLayout(info_vbox)
        body_lay.addWidget(profile_card)

        # Nota al pie informativa
        lbl_aviso = QLabel("💡 Se guardarán tus cambios y volverás a la pantalla de acceso.")
        lbl_aviso.setStyleSheet("color: #64748b; font-size: 12px; border: none;")
        body_lay.addWidget(lbl_aviso)

        root.addWidget(body)

        # ── Barra de Botones Inferior ─────────────────────────────────────────
        footer = QFrame()
        footer.setObjectName("logout_footer")
        footer.setStyleSheet("""
            #logout_footer {
                background-color: #0b1120;
                border-top: 1px solid #1e293b;
            }
        """)
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(24, 16, 24, 16)
        footer_lay.setSpacing(14)
        footer_lay.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setFixedSize(120, 42)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1.5px solid #334155;
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
                padding: 0 16px;
                min-height: 42px;
                max-height: 42px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
                border-color: #475569;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        footer_lay.addWidget(btn_cancel, 0, Qt.AlignVCenter)

        btn_confirm = QPushButton(" Cerrar Sesión")
        btn_confirm.setCursor(Qt.PointingHandCursor)
        btn_confirm.setFixedSize(165, 42)
        btn_confirm.setIcon(QIcon("assets/logout_icon_white.png"))
        btn_confirm.setIconSize(QSize(18, 18))
        btn_confirm.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ef4444, stop:1 #dc2626);
                color: #ffffff;
                border: 1.5px solid #f87171;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                padding: 0 16px;
                min-height: 42px;
                max-height: 42px;
            }
            QPushButton:hover {
                background: #f87171;
                border-color: #fca5a5;
            }
            QPushButton:pressed {
                background: #b91c1c;
            }
        """)
        btn_confirm.clicked.connect(self.accept)
        footer_lay.addWidget(btn_confirm, 0, Qt.AlignVCenter)

        root.addWidget(footer)


class MainWindow(QMainWindow):
    def __init__(self, usuario: Usuario):
        super().__init__()
        self.usuario = usuario
        self.solicito_cerrar_sesion = False
        self._timer_alertas = None
        self._widgets: dict[str, QWidget] = {}
        self._build_ui()
        self._iniciar_alertas_timer()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")

        # Asegurar barra de título estándar con todos los botones de control visibles (minimizar, maximizar, cerrar)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinMaxButtonsHint
            | Qt.WindowCloseButtonHint
        )

        # El tamaño de restauración (cuando el usuario des-maximiza) será 1280x760 centrado
        # Esto lo fija el sistema operativo automáticamente; no hacer resize/move manual aquí
        # porque interfiere con showMaximized() y da la apariencia de "falso maximizado"
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            # Sólo fijar el tamaño de restauración, no la posición
            self.resize(min(1280, geo.width()), min(760, geo.height()))

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        es_admin = self.usuario.es_admin()

        # ── Barra lateral ─────────────────────────────────────────────────────
        sidebar_container = QFrame()
        sidebar_container.setFixedWidth(220)
        sidebar_container.setStyleSheet(
            f"background: {PALETTE['bg_surface']}; "
            f"border-right: 1px solid {PALETTE['border']};"
        )
        sidebar_lay = QVBoxLayout(sidebar_container)
        sidebar_lay.setContentsMargins(0, 0, 0, 0)
        sidebar_lay.setSpacing(0)

        # Logo / Cabecera
        logo_frame = QFrame()
        logo_frame.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0f172a, stop:1 {PALETTE['bg_surface']});
            border-bottom: 1px solid {PALETTE['border']};
        """)
        logo_frame.setFixedHeight(82)
        logo_lay = QVBoxLayout(logo_frame)
        logo_lay.setContentsMargins(18, 12, 18, 12)
        logo_lay.setSpacing(3)

        lbl_logo = QLabel(APP_NAME)
        lbl_logo.setAlignment(Qt.AlignCenter)
        lbl_logo.setStyleSheet(
            f"color: {PALETTE['white']}; font-size: 15px; font-weight: bold; "
            "background: transparent; letter-spacing: 0.5px;"
        )
        logo_lay.addWidget(lbl_logo)

        rol_badge = self.usuario.rol_display
        lbl_user = QLabel(f"{self.usuario.username}  ·  {rol_badge}")
        lbl_user.setAlignment(Qt.AlignCenter)
        lbl_user.setStyleSheet(
            f"color: {PALETTE['accent']}; font-size: 11px; "
            "background: transparent; font-weight: 600;"
        )
        logo_lay.addWidget(lbl_user)

        sidebar_lay.addWidget(logo_frame)

        # Separador
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {PALETTE['border']}; border: none;")
        sidebar_lay.addWidget(sep)

        # Lista de navegación según Rol
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")

        secciones_visibles = SECCIONES_ADMIN if es_admin else SECCIONES_CAJERO


        for nombre, _ in secciones_visibles:
            item = QListWidgetItem(nombre)
            item.setFont(QFont("Segoe UI", 11))
            self.sidebar.addItem(item)

        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self._cambiar_seccion)
        sidebar_lay.addWidget(self.sidebar, 1)

        # Separador inferior
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {PALETTE['border']}; border: none;")
        sidebar_lay.addWidget(sep2)

        # Botones inferiores
        if es_admin:
            btn_respaldo = QPushButton("💾  Respaldar BD")
            btn_respaldo.clicked.connect(self._respaldar)
            btn_respaldo.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {PALETTE['text_secondary']};
                    border: none;
                    padding: 11px 18px;
                    text-align: left;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: rgba(255,255,255,0.05);
                    color: {PALETTE['text_primary']};
                }}
            """)
            sidebar_lay.addWidget(btn_respaldo)

        # Contenedor inferior para Cerrar Sesión con separación segura del borde
        bottom_box = QFrame()
        bottom_lay = QVBoxLayout(bottom_box)
        bottom_lay.setContentsMargins(12, 8, 12, 14)
        bottom_lay.setSpacing(6)

        btn_salir = QPushButton("🚪  Cerrar Sesión")
        btn_salir.setCursor(Qt.PointingHandCursor)
        btn_salir.setFixedHeight(42)
        btn_salir.clicked.connect(self._cerrar_sesion)
        btn_salir.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(239, 68, 68, 0.20), stop:1 rgba(220, 38, 38, 0.12));
                color: #fecaca;
                border: 1.5px solid rgba(239, 68, 68, 0.5);
                border-radius: 9px;
                padding: 0px 14px;
                text-align: center;
                font-size: 13px;
                font-weight: bold;
                letter-spacing: 0.3px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ef4444, stop:1 #dc2626);
                color: #ffffff;
                border-color: #f87171;
            }
            QPushButton:pressed {
                background: #b91c1c;
                color: #ffffff;
            }
        """)
        bottom_lay.addWidget(btn_salir)
        sidebar_lay.addWidget(bottom_box)

        root.addWidget(sidebar_container)

        # ── Área de contenido ─────────────────────────────────────────────────
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # Crear los widgets correspondientes a las secciones visibles del rol
        claves = [s[1] for s in secciones_visibles]
        constructores = {
            "pos":        lambda: POSWidget(self.usuario),
            "caja":       lambda: CajaWidget(self.usuario),
            "productos":  lambda: ProductosWidget(self.usuario),
            "compras":    lambda: ComprasWidget(self.usuario),
            "ventas":     lambda: VentasWidget(self.usuario),
            "reportes":   lambda: ReportesWidget(self.usuario),
            "inventario": lambda: InventarioWidget(self.usuario),
            "maestros":   lambda: MaestrosWidget(),
            "usuarios":   lambda: UsuariosWidget(self.usuario),
        }
        for clave in claves:
            w = constructores[clave]()
            self._widgets[clave] = w
            self.stack.addWidget(w)

        if claves:
            self._cambiar_seccion(0)

        # ── Barra de estado ───────────────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.lbl_status = QLabel(f"Sistema listo  |  DB: {DB_PATH}")
        self.lbl_status.setStyleSheet(f"color: {PALETTE['text_muted']};")
        self.status.addWidget(self.lbl_status)

        self.lbl_alertas = QLabel("")
        self.lbl_alertas.setStyleSheet(f"color: {PALETTE['warning']}; font-weight: bold;")
        self.status.addPermanentWidget(self.lbl_alertas)

    def _cambiar_seccion(self, index: int):
        self.stack.setCurrentIndex(index)
        widget = self.stack.currentWidget()
        if hasattr(widget, "actualizar") and callable(widget.actualizar):
            try:
                widget.actualizar()
            except Exception:
                pass

    def _iniciar_alertas_timer(self):
        """Revisa alertas de stock cada 60 segundos."""
        self._verificar_alertas()
        self._timer_alertas = QTimer(self)
        self._timer_alertas.timeout.connect(self._verificar_alertas)
        self._timer_alertas.start(60_000)

    def _verificar_alertas(self):
        session = SessionLocal()
        try:
            bajos = productos_con_stock_bajo(session)
            if bajos:
                self.lbl_alertas.setText(f"⚠ {len(bajos)} producto(s) con stock bajo")
            else:
                self.lbl_alertas.setText("")
        finally:
            session.close()

    def _respaldar(self):
        destino_dir = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de respaldo", str(Path.home())
        )
        if not destino_dir:
            return
        try:
            archivo = respaldar_base_de_datos(DB_PATH, Path(destino_dir))
            QMessageBox.information(
                self, "Respaldo exitoso",
                f"Base de datos respaldada en:\n{archivo}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo realizar el respaldo: {e}")

    def _cerrar_sesion(self):
        dlg = CerrarSesionDialog(self.usuario, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.solicito_cerrar_sesion = True
            self.close()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_maximizacion_inicial_aplicada", False):
            self._maximizacion_inicial_aplicada = True
            roles = self.usuario.get_roles() if hasattr(self.usuario, "get_roles") else [self.usuario.rol]
            debe_maximizar = (
                self.usuario.es_admin()
                or self.usuario.tiene_rol("admin")
                or (hasattr(self.usuario, "tiene_doble_rol") and self.usuario.tiene_doble_rol())
                or len(roles) >= 2
            )
            if debe_maximizar:
                QTimer.singleShot(0, self._aplicar_maximizacion)

    def _aplicar_maximizacion(self):
        """Maximiza la ventana asegurando que la barra de título y los botones de control sean visibles."""
        self.showMaximized()

    def closeEvent(self, event):
        if hasattr(self, "_timer_alertas") and self._timer_alertas:
            self._timer_alertas.stop()

        for w in self._widgets.values():
            if hasattr(w, "close"):
                try:
                    w.close()
                except Exception:
                    pass

        QApplication.instance().quit()
        event.accept()
