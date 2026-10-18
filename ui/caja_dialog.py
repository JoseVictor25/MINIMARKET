"""
ui/caja_dialog.py – Diálogos para Apertura, Cierre y Arqueo de Caja.
Diseñados con fuente legible de 14px, acabado estético moderno y flujo intuitivo.
"""
from __future__ import annotations

import os
from decimal import Decimal
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QDate, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QDateEdit, QFrame, QMessageBox, QTextEdit,
    QScrollArea, QWidget, QStyledItemDelegate,
)
from PyQt5.QtGui import QFont, QDoubleValidator

from database import get_session, SessionLocal
from models.usuario import Usuario
from models.caja import SesionCaja
from services.caja_service import (
    abrir_caja,
    obtener_resumen_caja,
    cerrar_caja,
    generar_ticket_arqueo_pdf,
)
from config import CURRENCY, APP_NAME
from ui.styles import PALETTE, configurar_calendario_elegante


# ══════════════════════════════════════════════════════════════════════════════
#  FORMULARIO DE APERTURA DE CAJA
# ══════════════════════════════════════════════════════════════════════════════

class AperturaCajaDialog(QDialog):
    """
    Formulario de Apertura de Caja.
    Replica la distribución exacta solicitada:
      - Cajero
      - Turno
      - Fecha Apertura
      - Total Bs Apertura
      - Botones: Grabar, Cancelar, Salir
    """

    def __init__(self, usuario_actual: Usuario, parent=None):
        super().__init__(parent)
        self.usuario_actual = usuario_actual
        self.sesion_creada: SesionCaja | None = None

        self.setWindowTitle("Formulario de Apertura de Caja")
        self.setFixedWidth(580)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {PALETTE['bg_base']};
                color: {PALETTE['white']};
            }}
        """)
        self._build_ui()
        self._cargar_cajeros()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(16)

        # ── Encabezado Moderno con Icono ──────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(14)

        icon_frame = QFrame()
        icon_frame.setFixedSize(48, 48)
        icon_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #059669, stop:1 #10b981);
                border-radius: 12px;
                border: 1px solid #34d399;
            }
        """)
        icon_lay = QVBoxLayout(icon_frame)
        icon_lay.setContentsMargins(0, 0, 0, 0)
        lbl_ico = QLabel("🔓")
        lbl_ico.setAlignment(Qt.AlignCenter)
        lbl_ico.setStyleSheet("font-size: 24px; background: transparent; border: none;")
        icon_lay.addWidget(lbl_ico)
        hdr.addWidget(icon_frame)

        hdr_texts = QVBoxLayout()
        hdr_texts.setSpacing(2)
        lbl_tit = QLabel("Formulario de Apertura de Caja")
        lbl_tit.setStyleSheet("font-size: 17px; font-weight: bold; color: #ffffff; background: transparent; border: none;")
        hdr_texts.addWidget(lbl_tit)

        lbl_sub = QLabel("Registre el cajero responsable, turno y el efectivo inicial de apertura.")
        lbl_sub.setStyleSheet("color: #94a3b8; font-size: 12px; background: transparent; border: none;")
        hdr_texts.addWidget(lbl_sub)
        hdr.addLayout(hdr_texts)
        hdr.addStretch()
        root.addLayout(hdr)

        # ── Contenedor de Formulario (Card) ───────────────────────────
        form_card = QFrame()
        form_card.setObjectName("form_card_apertura")
        form_card.setStyleSheet("""
            QFrame#form_card_apertura {
                background: #16202e;
                border: 1px solid #283548;
                border-radius: 12px;
            }
            QLabel {
                color: #94a3b8;
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 0.8px;
                background: transparent;
                border: none;
            }
            QLineEdit, QComboBox, QDateEdit {
                background: #101722;
                color: #ffffff;
                border: 1.5px solid #2e3c50;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 14px;
                min-height: 40px;
            }
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
                border: 2px solid #0ea5e9;
                background: #131c2a;
            }
            QComboBox::drop-down, QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border-left: 1px solid #2e3c50;
                border-top-right-radius: 7px;
                border-bottom-right-radius: 7px;
                background-color: #101722;
            }
            QComboBox::down-arrow, QDateEdit::down-arrow {
                image: url(assets/combo_arrow.png);
                width: 12px;
                height: 12px;
            }
        """)

        grid = QGridLayout(form_card)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        grid.setContentsMargins(18, 16, 18, 18)

        # Fila 0: Labels de Cajero y Turno
        lbl_cajero = QLabel("CAJERO RESPONSABLE *")
        grid.addWidget(lbl_cajero, 0, 0)

        lbl_turno = QLabel("TURNO *")
        grid.addWidget(lbl_turno, 0, 1)

        # Fila 1: Inputs de Cajero y Turno
        self.combo_cajero = QComboBox()
        self.combo_cajero.setFixedHeight(40)
        self.combo_cajero.setItemDelegate(QStyledItemDelegate(self.combo_cajero))
        self.combo_cajero.setMaxVisibleItems(8)
        grid.addWidget(self.combo_cajero, 1, 0)

        self.combo_turno = QComboBox()
        self.combo_turno.setFixedHeight(40)
        self.combo_turno.setItemDelegate(QStyledItemDelegate(self.combo_turno))
        turnos = [
            ("☀️  Mañana", "Mañana"),
            ("🌤️  Tarde", "Tarde"),
            ("🌙  Noche", "Noche"),
            ("⏰  Completo", "Completo"),
        ]
        for txt, val in turnos:
            self.combo_turno.addItem(txt, val)
        grid.addWidget(self.combo_turno, 1, 1)

        # Fila 2: Labels de Fecha y Monto
        lbl_fecha = QLabel("FECHA DE APERTURA")
        grid.addWidget(lbl_fecha, 2, 0)

        lbl_total_bs = QLabel(f"TOTAL APERTURA ({CURRENCY}) *")
        lbl_total_bs.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold; letter-spacing: 0.8px;")
        grid.addWidget(lbl_total_bs, 2, 1)

        # Fila 3: Inputs de Fecha y Monto
        self.date_apertura = QDateEdit()
        self.date_apertura.setFixedHeight(40)
        self.date_apertura.setCalendarPopup(True)
        self.date_apertura.setDate(QDate.currentDate())
        self.date_apertura.setDisplayFormat("dd/MM/yyyy")
        configurar_calendario_elegante(self.date_apertura)
        grid.addWidget(self.date_apertura, 3, 0)

        self.input_total_bs = QLineEdit()
        self.input_total_bs.setFixedHeight(40)
        self.input_total_bs.setPlaceholderText("0.00")
        self.input_total_bs.setText("0.00")
        self.input_total_bs.setAlignment(Qt.AlignRight)
        self.input_total_bs.setStyleSheet("""
            QLineEdit {
                background: #101722;
                color: #ffffff;
                border: 1.5px solid #0ea5e9;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QLineEdit:focus {
                border: 2px solid #38bdf8;
                background: #131c2a;
            }
        """)
        grid.addWidget(self.input_total_bs, 3, 1)

        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 5)

        root.addWidget(form_card)

        # ── Botonera: Limpiar (izquierda), Cancelar y Abrir Caja (derecha) ─────
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(12)

        self.btn_cancelar = QPushButton("↺  Limpiar")
        self.btn_cancelar.setFixedHeight(40)
        self.btn_cancelar.setCursor(Qt.PointingHandCursor)
        self.btn_cancelar.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #94a3b8;
                font-size: 13px;
                font-weight: 600;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background: #334155;
                color: #ffffff;
            }
        """)
        self.btn_cancelar.clicked.connect(self._cancelar)
        btn_bar.addWidget(self.btn_cancelar)

        btn_bar.addStretch()

        self.btn_salir = QPushButton("Cancelar")
        self.btn_salir.setFixedHeight(40)
        self.btn_salir.setFixedWidth(110)
        self.btn_salir.setCursor(Qt.PointingHandCursor)
        self.btn_salir.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #cbd5e1;
                font-size: 13px;
                font-weight: 600;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: #334155;
                color: #ffffff;
            }
        """)
        self.btn_salir.clicked.connect(self.reject)
        btn_bar.addWidget(self.btn_salir)

        self.btn_grabar = QPushButton("✓  Abrir Caja")
        self.btn_grabar.setFixedHeight(40)
        self.btn_grabar.setMinimumWidth(150)
        self.btn_grabar.setCursor(Qt.PointingHandCursor)
        self.btn_grabar.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #059669, stop:1 #047857);
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #34d399;
                border-radius: 8px;
                padding: 0 22px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #10b981, stop:1 #059669);
                border-color: #6ee7b7;
            }
            QPushButton:pressed {
                background: #065f46;
            }
        """)
        self.btn_grabar.clicked.connect(self._grabar)
        btn_bar.addWidget(self.btn_grabar)

        root.addLayout(btn_bar)

    def _cargar_cajeros(self):
        """Carga los usuarios activos y preselecciona al usuario actual."""
        with get_session() as session:
            usuarios = session.query(Usuario).filter(Usuario.activo == True).order_by(Usuario.nombre_completo).all()
            self.combo_cajero.clear()
            idx_seleccion = 0
            for i, u in enumerate(usuarios):
                self.combo_cajero.addItem(f"👤  {u.nombre_completo} ({u.username})", u.id)
                if u.id == self.usuario_actual.id:
                    idx_seleccion = i

            if self.combo_cajero.count() > 0:
                self.combo_cajero.setCurrentIndex(idx_seleccion)

    def _cancelar(self):
        """Limpia los campos a valores por defecto."""
        self.input_total_bs.setText("0.00")
        self.combo_turno.setCurrentIndex(0)
        self.date_apertura.setDate(QDate.currentDate())
        self.input_total_bs.setFocus()

    def _grabar(self):
        """Valida y abre la sesión de caja en la base de datos."""
        txt_monto = self.input_total_bs.text().strip().replace(",", ".")
        try:
            monto_inicial = Decimal(txt_monto) if txt_monto else Decimal("0.00")
            if monto_inicial < 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(
                self,
                "Monto Inválido",
                "Por favor ingrese un monto inicial válido en Total Bs Apertura (ej. 100.00 o 0.00)."
            )
            self.input_total_bs.setFocus()
            return

        usuario_id = self.combo_cajero.currentData()
        if not usuario_id:
            QMessageBox.warning(self, "Cajero Requerido", "Debe seleccionar un cajero.")
            return

        turno = self.combo_turno.currentData() or self.combo_turno.currentText()
        qdate = self.date_apertura.date()
        fecha_apertura = datetime(qdate.year(), qdate.month(), qdate.day(), datetime.now().hour, datetime.now().minute, datetime.now().second)

        try:
            with get_session() as session:
                caja = abrir_caja(
                    session=session,
                    usuario_id=usuario_id,
                    turno=turno,
                    monto_inicial_bs=monto_inicial,
                    fecha_apertura=fecha_apertura,
                    observacion=f"Apertura de turno {turno}",
                )
                session.flush()
                self.sesion_creada = caja

            cajero_txt = self.combo_cajero.currentText().replace("👤", "").strip()
            dlg_exito = AperturaExitosaDialog(
                cajero_nombre=cajero_txt,
                turno=turno,
                monto_inicial=monto_inicial,
                fecha_str=fecha_apertura.strftime("%d/%m/%Y %H:%M"),
                parent=self,
            )
            dlg_exito.exec_()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error al Abrir Caja", f"No se pudo registrar la apertura de caja:\n{e}")


# ══════════════════════════════════════════════════════════════════════════════
#  MODALES MODERNOS DE CONFIRMACIÓN Y ÉXITO DE APERTURA DE CAJA
# ══════════════════════════════════════════════════════════════════════════════

class AperturaExitosaDialog(QDialog):
    """Modal de confirmación visual y elegante tras abrir caja con éxito."""

    def __init__(self, cajero_nombre: str, turno: str, monto_inicial: Decimal, fecha_str: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Apertura Exitosa")
        self.setFixedWidth(460)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(28, 24, 28, 20)
        body_lay.setSpacing(16)

        # Header con icono badge verde
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        icon_badge = QLabel("✓")
        icon_badge.setFixedSize(54, 54)
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setStyleSheet("""
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                stop:0 rgba(16, 185, 129, 0.25), stop:1 rgba(16, 185, 129, 0.08));
            border: 2px solid rgba(16, 185, 129, 0.5);
            border-radius: 27px;
            color: #10b981;
            font-size: 26px;
            font-weight: bold;
        """)
        top_row.addWidget(icon_badge)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        lbl_title = QLabel("¡Caja Abierta con Éxito!")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff; border: none;")
        lbl_sub = QLabel("La sesión de caja está lista para registrar ventas.")
        lbl_sub.setStyleSheet("font-size: 13px; color: #94a3b8; border: none;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        top_row.addLayout(title_box)
        top_row.addStretch()

        body_lay.addLayout(top_row)

        # Card de detalles
        card = QFrame()
        card.setObjectName("info_card")
        card.setStyleSheet("""
            #info_card {
                background-color: #1a2436;
                border: 1px solid #2e3e55;
                border-radius: 12px;
                padding: 12px 16px;
            }
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setSpacing(8)

        def fila(label, valor, valor_color="#ffffff"):
            r = QHBoxLayout()
            lt = QLabel(label)
            lt.setStyleSheet("color: #94a3b8; font-size: 13px; border: none;")
            lv = QLabel(valor)
            lv.setStyleSheet(f"color: {valor_color}; font-size: 13px; font-weight: bold; border: none;")
            r.addWidget(lt)
            r.addStretch()
            r.addWidget(lv)
            return r

        card_lay.addLayout(fila("👤 Cajero Responsable:", cajero_nombre))
        card_lay.addLayout(fila("⏰ Turno de Caja:", turno))
        card_lay.addLayout(fila("💵 Base Inicial:", f"{CURRENCY} {monto_inicial:.2f}", "#10b981"))
        card_lay.addLayout(fila("📅 Fecha y Hora:", fecha_str))

        body_lay.addWidget(card)
        root.addWidget(body)

        footer = QFrame()
        footer.setStyleSheet(f"background-color: {PALETTE['bg_surface']}; border-top: 1px solid {PALETTE['border']};")
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(24, 14, 24, 16)
        footer_lay.addStretch()

        btn_ok = QPushButton("✓  Comenzar a Operar")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setFixedHeight(40)
        btn_ok.setMinimumWidth(180)
        btn_ok.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #059669, stop:1 #047857);
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #34d399;
                border-radius: 8px;
                padding: 0 20px;
            }
            QPushButton:hover {
                background: #10b981;
            }
        """)
        btn_ok.clicked.connect(self.accept)
        footer_lay.addWidget(btn_ok)
        root.addWidget(footer)


class ConfirmarAperturaPromptDialog(QDialog):
    """Diálogo modal moderno que solicita al usuario abrir caja antes de registrar ventas."""

    def __init__(self, usuario: Usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Caja Cerrada - Apertura Requerida")
        self.setFixedWidth(460)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(28, 24, 28, 20)
        body_lay.setSpacing(16)

        # Header
        hdr = QHBoxLayout()
        hdr.setSpacing(16)

        badge = QLabel("🔓")
        badge.setFixedSize(54, 54)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet("""
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                stop:0 rgba(245, 158, 11, 0.25), stop:1 rgba(245, 158, 11, 0.08));
            border: 2px solid rgba(245, 158, 11, 0.5);
            border-radius: 27px;
            font-size: 26px;
        """)
        hdr.addWidget(badge)

        vbox = QVBoxLayout()
        vbox.setSpacing(3)
        lbl_t = QLabel("Apertura Requerida")
        lbl_t.setStyleSheet("font-size: 19px; font-weight: bold; color: #ffffff; border: none;")
        lbl_s = QLabel("No hay una sesión de caja activa en el sistema.")
        lbl_s.setStyleSheet("font-size: 13px; color: #94a3b8; border: none;")
        vbox.addWidget(lbl_t)
        vbox.addWidget(lbl_s)
        hdr.addLayout(vbox)
        hdr.addStretch()
        body_lay.addLayout(hdr)

        # Info card
        card = QFrame()
        card.setStyleSheet("""
            background-color: #1a2436;
            border: 1px solid #2e3e55;
            border-radius: 12px;
            padding: 12px 16px;
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setSpacing(6)
        nombre = self.usuario.nombre_completo or self.usuario.username
        lbl_user = QLabel(f"<b>Cajero:</b> {nombre} (@{self.usuario.username})")
        lbl_user.setStyleSheet("color: #ffffff; font-size: 13px; border: none;")
        lbl_note = QLabel("Para registrar ventas y cobrar en el Punto de Venta, primero debe abrir su turno de caja.")
        lbl_note.setWordWrap(True)
        lbl_note.setStyleSheet("color: #94a3b8; font-size: 12px; border: none;")
        card_lay.addWidget(lbl_user)
        card_lay.addWidget(lbl_note)
        body_lay.addWidget(card)

        root.addWidget(body)

        footer = QFrame()
        footer.setStyleSheet(f"background-color: {PALETTE['bg_surface']}; border-top: 1px solid {PALETTE['border']};")
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(24, 14, 24, 16)
        footer_lay.setSpacing(12)
        footer_lay.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setFixedSize(110, 40)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['bg_hover']};
                color: #cbd5e1;
                border: 1px solid {PALETTE['border']};
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{ background-color: {PALETTE['border']}; color: #ffffff; }}
        """)
        btn_cancel.clicked.connect(self.reject)
        footer_lay.addWidget(btn_cancel)

        btn_open = QPushButton("🔓  Abrir Caja Ahora")
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.setFixedHeight(40)
        btn_open.setMinimumWidth(165)
        btn_open.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #059669, stop:1 #047857);
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #34d399;
                border-radius: 8px;
                padding: 0 16px;
            }
            QPushButton:hover { background: #10b981; }
        """)
        btn_open.clicked.connect(self.accept)
        footer_lay.addWidget(btn_open)

        root.addWidget(footer)


# ══════════════════════════════════════════════════════════════════════════════
#  MODAL DE CONFIRMACIÓN AMIGABLE DE CIERRE DE CAJA
# ══════════════════════════════════════════════════════════════════════════════

class ConfirmarCierreDialog(QDialog):
    """
    Diálogo modal de confirmación con diseño estético premium,
    resumen visual de cifras y botones claros en español.
    """

    def __init__(
        self,
        sesion_id: int,
        cajero: str,
        turno: str,
        esperado: Decimal,
        fisico: Decimal,
        diferencia: Decimal,
        estado_arqueo_txt: str,
        parent=None,
    ):
        super().__init__(parent)
        self.sesion_id = sesion_id
        self.cajero = cajero
        self.turno = turno
        self.esperado = esperado
        self.fisico = fisico
        self.diferencia = diferencia
        self.estado_arqueo_txt = estado_arqueo_txt

        self.setWindowTitle("Confirmar Cierre de Caja")
        self.setFixedWidth(540)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {PALETTE['bg_base']};
                color: {PALETTE['white']};
            }}
        """)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(16)

        # ── Encabezado con Icono ──────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(14)

        lbl_icon = QLabel("🔒")
        lbl_icon.setStyleSheet("font-size: 32px; background: transparent;")
        hdr.addWidget(lbl_icon)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        lbl_tit = QLabel(f"¿Cerrar y Finalizar Caja #{self.sesion_id}?")
        lbl_tit.setFont(QFont("Segoe UI", 15, QFont.Bold))
        lbl_tit.setStyleSheet(f"color: {PALETTE['white']}; background: transparent;")
        title_vbox.addWidget(lbl_tit)

        lbl_sub = QLabel(f"Cajero: {self.cajero}   ·   Turno: {self.turno}")
        lbl_sub.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px; background: transparent;")
        title_vbox.addWidget(lbl_sub)

        hdr.addLayout(title_vbox)
        hdr.addStretch()
        root.addLayout(hdr)

        # ── Tarjeta de Cifras Finales ─────────────────────────────────────────
        card = QFrame()
        card.setObjectName("card_confirmacion")
        card.setStyleSheet(f"""
            QFrame#card_confirmacion {{
                background: {PALETTE['bg_card']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 12px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        c_lay = QVBoxLayout(card)
        c_lay.setContentsMargins(18, 16, 18, 16)
        c_lay.setSpacing(10)

        def fila(titulo: str, valor: str, color_val: str = "#ffffff", bold: bool = True):
            row = QHBoxLayout()
            l_t = QLabel(titulo)
            l_t.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 14px;")
            row.addWidget(l_t)
            row.addStretch()
            l_v = QLabel(valor)
            peso = "bold" if bold else "normal"
            l_v.setStyleSheet(f"color: {color_val}; font-size: 15px; font-weight: {peso};")
            row.addWidget(l_v)
            c_lay.addLayout(row)

        fila("💵 Efectivo Esperado (Sistema):", f"{CURRENCY} {self.esperado:.2f}", color_val=PALETTE['accent_hover'])
        fila("💰 Efectivo Físico Contado:", f"{CURRENCY} {self.fisico:.2f}", color_val="#ffffff")

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {PALETTE['border']};")
        c_lay.addWidget(sep)

        # Estado del arqueo con color adecuado
        if self.diferencia == Decimal("0.00"):
            badge_color = PALETTE['success']
            badge_bg = "rgba(34, 197, 94, 0.15)"
            badge_border = PALETTE['success']
        elif self.diferencia > 0:
            badge_color = PALETTE['accent_hover']
            badge_bg = "rgba(79, 142, 247, 0.15)"
            badge_border = PALETTE['accent']
        else:
            badge_color = PALETTE['danger']
            badge_bg = "rgba(239, 68, 68, 0.15)"
            badge_border = PALETTE['danger']

        badge = QLabel(self.estado_arqueo_txt)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedHeight(36)
        badge.setStyleSheet(f"""
            background: {badge_bg};
            color: {badge_color};
            border: 1px solid {badge_border};
            border-radius: 8px;
            font-size: 13px;
            font-weight: bold;
            padding: 4px 10px;
        """)
        c_lay.addWidget(badge)
        root.addWidget(card)

        # ── Mensaje de Advertencia Amigable ───────────────────────────────────
        adv_box = QFrame()
        adv_box.setStyleSheet("""
            background: rgba(245, 158, 11, 0.1);
            border: 1px solid #f59e0b;
            border-radius: 8px;
        """)
        adv_lay = QHBoxLayout(adv_box)
        adv_lay.setContentsMargins(14, 10, 14, 10)
        adv_lay.setSpacing(10)

        lbl_warn_ico = QLabel("⚠️")
        lbl_warn_ico.setStyleSheet("font-size: 18px; background: transparent; border: none;")
        adv_lay.addWidget(lbl_warn_ico)

        lbl_warn_txt = QLabel("Una vez confirmada, la sesión quedará sellada definitivamente y no se podrán registrar nuevas ventas con este turno.")
        lbl_warn_txt.setWordWrap(True)
        lbl_warn_txt.setStyleSheet("color: #fbbf24; font-size: 13px; font-weight: 500; background: transparent; border: none;")
        adv_lay.addWidget(lbl_warn_txt, 1)
        root.addWidget(adv_box)

        # ── Botonera en Español y de Gran Tamaño ─────────────────────────────
        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(12)

        btn_cancelar = QPushButton("←  No, Volver")
        btn_cancelar.setFixedHeight(46)
        btn_cancelar.setCursor(Qt.PointingHandCursor)
        btn_cancelar.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['bg_hover']};
                color: {PALETTE['text_primary']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: {PALETTE['bg_card']};
                color: white;
            }}
        """)
        btn_cancelar.clicked.connect(self.reject)
        btn_lay.addWidget(btn_cancelar, 1)

        btn_confirmar = QPushButton("✓  Sí, Cerrar Caja")
        btn_confirmar.setFixedHeight(46)
        btn_confirmar.setCursor(Qt.PointingHandCursor)
        btn_confirmar.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 0 16px;
            }
            QPushButton:hover {
                background: #ef4444;
            }
            QPushButton:pressed {
                background: #b91c1c;
            }
        """)
        btn_confirmar.clicked.connect(self.accept)
        btn_lay.addWidget(btn_confirmar, 2)

        root.addLayout(btn_lay)


# ══════════════════════════════════════════════════════════════════════════════
#  FORMULARIO DE CIERRE Y ARQUEO DE CAJA
# ══════════════════════════════════════════════════════════════════════════════

class CierreCajaDialog(QDialog):
    """
    Formulario de Arqueo y Cierre de Caja con diseño espacioso,
    tipografía de alta legibilidad y prevención de compresión de texto.
    """

    def __init__(self, sesion_caja_id: int, parent=None):
        super().__init__(parent)
        self.sesion_caja_id = sesion_caja_id
        self.resumen: dict = {}
        self.diferencia = Decimal("0.00")
        self.cierre_completado = False

        self.setWindowTitle("Control y Arqueo de Caja – Cierre de Turno")
        self.setMinimumSize(660, 720)
        self.resize(680, 760)
        self.setModal(True)
        self._cargar_datos()
        self._build_ui()
        self._actualizar_arqueo()

    def _cargar_datos(self):
        with get_session() as session:
            self.resumen = obtener_resumen_caja(session, self.sesion_caja_id)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # ── Scroll Area para garantizar que NUNCA se comprima el texto en ninguna pantalla
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        s_lay = QVBoxLayout(scroll_content)
        s_lay.setContentsMargins(2, 2, 8, 2)
        s_lay.setSpacing(14)

        # ── 1. Encabezado de Sesión ──────────────────────────────────────────
        header = QFrame()
        header.setObjectName("hdr_cierre")
        header.setStyleSheet(f"""
            QFrame#hdr_cierre {{
                background: {PALETTE['bg_card']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 10px;
            }}
        """)
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(16, 12, 16, 12)
        h_lay.setSpacing(6)

        t_lay = QHBoxLayout()
        lbl_ico = QLabel("🔒")
        lbl_ico.setStyleSheet("font-size: 24px; background: transparent; border: none;")
        t_lay.addWidget(lbl_ico)

        lbl_tit = QLabel(f"Cierre y Arqueo de Caja #{self.resumen['sesion_id']}")
        lbl_tit.setFont(QFont("Segoe UI", 15, QFont.Bold))
        lbl_tit.setStyleSheet(f"color: {PALETTE['white']}; background: transparent; border: none;")
        t_lay.addWidget(lbl_tit)
        t_lay.addStretch()
        h_lay.addLayout(t_lay)

        f_ap = self.resumen['fecha_apertura'].strftime("%d/%m/%Y %H:%M") if self.resumen['fecha_apertura'] else "-"
        lbl_sub = QLabel(
            f"👤 Cajero: <b>{self.resumen['usuario_nombre']}</b>   |   Turno: <b>{self.resumen['turno']}</b>   |   Apertura: <b>{f_ap}</b>"
        )
        lbl_sub.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px; background: transparent; border: none;")
        h_lay.addWidget(lbl_sub)
        s_lay.addWidget(header)

        # ── 2. Card: Resumen de Ventas del Sistema ───────────────────────────
        res_card = QFrame()
        res_card.setObjectName("card_resumen_ventas")
        res_card.setStyleSheet(f"""
            QFrame#card_resumen_ventas {{
                background: {PALETTE['bg_surface']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 12px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        r_lay = QVBoxLayout(res_card)
        r_lay.setContentsMargins(18, 16, 18, 16)
        r_lay.setSpacing(10)

        lbl_sec1 = QLabel("📊  RESUMEN DE VENTAS DEL SISTEMA")
        lbl_sec1.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lbl_sec1.setStyleSheet(f"color: {PALETTE['accent']}; letter-spacing: 0.5px;")
        r_lay.addWidget(lbl_sec1)

        def fila_resumen(texto: str, valor: Decimal, es_destacado: bool = False, color: str = None):
            f = QHBoxLayout()
            lbl_t = QLabel(texto)
            lbl_t.setMinimumHeight(24)
            lbl_t.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 14px; font-weight: {'bold' if es_destacado else 'normal'};")
            f.addWidget(lbl_t)
            f.addStretch()

            lbl_v = QLabel(f"{CURRENCY} {valor:.2f}")
            lbl_v.setMinimumHeight(24)
            c_val = color or (PALETTE['white'] if es_destacado else PALETTE['text_primary'])
            peso = "bold" if es_destacado else "600"
            tam = "16px" if es_destacado else "14px"
            lbl_v.setStyleSheet(f"color: {c_val}; font-size: {tam}; font-weight: {peso};")
            f.addWidget(lbl_v)
            r_lay.addLayout(f)

        fila_resumen("(+) Base Inicial de Apertura:", self.resumen["base_inicial"])
        fila_resumen("(+) Ventas en Efectivo:", self.resumen["ventas_efectivo"])
        fila_resumen("    Ventas QR:", self.resumen["ventas_qr"])
        fila_resumen("    Ventas Tarjeta:", self.resumen["ventas_tarjeta"])
        if self.resumen["ventas_otros"] > 0:
            fila_resumen("    Otros Medios:", self.resumen["ventas_otros"])

        linea = QFrame()
        linea.setFixedHeight(1)
        linea.setStyleSheet(f"background: {PALETTE['border']};")
        r_lay.addWidget(linea)

        fila_resumen(
            f"TOTAL VENTAS ({self.resumen['cantidad_ventas']} transacciones):",
            self.resumen["total_ventas"],
            es_destacado=True,
            color=PALETTE['accent_hover'],
        )

        # Tarjeta Destacada: Total Efectivo Esperado en Caja
        esp_frame = QFrame()
        esp_frame.setObjectName("esp_frame")
        esp_frame.setStyleSheet(f"""
            QFrame#esp_frame {{
                background: rgba(37, 99, 235, 0.15);
                border: 2px solid {PALETTE['accent']};
                border-radius: 10px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        esp_lay = QHBoxLayout(esp_frame)
        esp_lay.setContentsMargins(16, 12, 16, 12)

        lbl_esp_t = QLabel("💵  TOTAL EFECTIVO ESPERADO EN CAJA:")
        lbl_esp_t.setStyleSheet(f"color: {PALETTE['white']}; font-size: 14px; font-weight: bold;")
        esp_lay.addWidget(lbl_esp_t)
        esp_lay.addStretch()

        self.lbl_esp_v = QLabel(f"{CURRENCY} {self.resumen['total_efectivo_esperado']:.2f}")
        self.lbl_esp_v.setStyleSheet(f"color: {PALETTE['accent_hover']}; font-size: 22px; font-weight: 900;")
        esp_lay.addWidget(self.lbl_esp_v)

        r_lay.addWidget(esp_frame)
        s_lay.addWidget(res_card)

        # ── 3. Card: Arqueo Físico y Diferencia ───────────────────────────────
        arq_card = QFrame()
        arq_card.setObjectName("card_arqueo_fisico")
        arq_card.setStyleSheet(f"""
            QFrame#card_arqueo_fisico {{
                background: {PALETTE['bg_card']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 12px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        a_lay = QVBoxLayout(arq_card)
        a_lay.setContentsMargins(18, 16, 18, 16)
        a_lay.setSpacing(12)

        lbl_sec2 = QLabel("💰  ARQUEO FÍSICO (DINERO EN CAJÓN)")
        lbl_sec2.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lbl_sec2.setStyleSheet(f"color: {PALETTE['warning']}; letter-spacing: 0.5px;")
        a_lay.addWidget(lbl_sec2)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        lbl_cont = QLabel("Efectivo Contado (Bs):")
        lbl_cont.setStyleSheet(f"color: {PALETTE['white']}; font-size: 15px; font-weight: bold;")
        input_row.addWidget(lbl_cont)

        self.input_fisico = QLineEdit()
        self.input_fisico.setText(f"{self.resumen['total_efectivo_esperado']:.2f}")
        self.input_fisico.setAlignment(Qt.AlignRight)
        self.input_fisico.setFixedHeight(46)
        self.input_fisico.setStyleSheet(f"""
            QLineEdit {{
                background: {PALETTE['bg_input']};
                color: {PALETTE['white']};
                border: 2px solid {PALETTE['accent']};
                border-radius: 8px;
                font-size: 20px;
                font-weight: bold;
                padding: 4px 12px;
                min-width: 150px;
            }}
            QLineEdit:focus {{
                border-color: {PALETTE['accent_hover']};
            }}
        """)
        self.input_fisico.textChanged.connect(self._actualizar_arqueo)
        input_row.addWidget(self.input_fisico)

        btn_cuadre = QPushButton("💰 Exacto")
        btn_cuadre.setToolTip("Rellenar automáticamente con el total esperado")
        btn_cuadre.setFixedHeight(46)
        btn_cuadre.setCursor(Qt.PointingHandCursor)
        btn_cuadre.setStyleSheet(f"""
            QPushButton {{
                background: rgba(37, 99, 235, 0.2);
                color: {PALETTE['accent_hover']};
                border: 1.5px solid {PALETTE['accent']};
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {PALETTE['accent']};
                color: white;
            }}
        """)
        btn_cuadre.clicked.connect(lambda: self.input_fisico.setText(f"{self.resumen['total_efectivo_esperado']:.2f}"))
        input_row.addWidget(btn_cuadre)
        a_lay.addLayout(input_row)

        # Badge Dinámico de Diferencia
        self.badge_dif = QLabel("✓  Caja Cuadrada (Bs 0.00)")
        self.badge_dif.setAlignment(Qt.AlignCenter)
        self.badge_dif.setFixedHeight(44)
        self.badge_dif.setStyleSheet(f"""
            background: rgba(34, 197, 94, 0.2);
            color: {PALETTE['success']};
            border: 1.5px solid {PALETTE['success']};
            border-radius: 8px;
            font-size: 15px;
            font-weight: bold;
        """)
        a_lay.addWidget(self.badge_dif)

        # Observaciones
        obs_lay = QHBoxLayout()
        obs_lay.setSpacing(10)
        lbl_obs = QLabel("Nota / Obs:")
        lbl_obs.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px; font-weight: 600;")
        obs_lay.addWidget(lbl_obs)

        self.input_obs = QLineEdit()
        self.input_obs.setPlaceholderText("Comentario u observación sobre el arqueo (opcional)...")
        self.input_obs.setFixedHeight(38)
        self.input_obs.setStyleSheet(f"""
            QLineEdit {{
                background: {PALETTE['bg_input']};
                color: {PALETTE['white']};
                border: 1px solid {PALETTE['border']};
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {PALETTE['accent']};
            }}
        """)
        obs_lay.addWidget(self.input_obs)
        a_lay.addLayout(obs_lay)

        s_lay.addWidget(arq_card)
        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

        # ── 4. Botonera Inferior Fija (Siempre visible) ────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_imprimir = QPushButton("📄  Ticket de Arqueo")
        self.btn_imprimir.setFixedHeight(46)
        self.btn_imprimir.setCursor(Qt.PointingHandCursor)
        self.btn_imprimir.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['bg_hover']};
                color: {PALETTE['text_primary']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: {PALETTE['bg_card']};
                color: white;
            }}
        """)
        self.btn_imprimir.clicked.connect(self._imprimir_arqueo)
        btn_row.addWidget(self.btn_imprimir)

        btn_row.addStretch()

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setFixedHeight(46)
        self.btn_cancelar.setCursor(Qt.PointingHandCursor)
        self.btn_cancelar.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['bg_hover']};
                color: {PALETTE['text_primary']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: {PALETTE['bg_card']};
                color: white;
            }}
        """)
        self.btn_cancelar.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancelar)

        self.btn_cerrar = QPushButton("🔒  Confirmar Cierre de Caja")
        self.btn_cerrar.setFixedHeight(46)
        self.btn_cerrar.setCursor(Qt.PointingHandCursor)
        self.btn_cerrar.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 0 18px;
            }
            QPushButton:hover {
                background: #ef4444;
            }
            QPushButton:pressed {
                background: #b91c1c;
            }
        """)
        self.btn_cerrar.clicked.connect(self._confirmar_cierre)
        btn_row.addWidget(self.btn_cerrar)

        root.addLayout(btn_row)

    def _actualizar_arqueo(self):
        txt = self.input_fisico.text().strip().replace(",", ".")
        try:
            monto_fisico = Decimal(txt) if txt else Decimal("0.00")
        except Exception:
            monto_fisico = Decimal("0.00")

        esperado = self.resumen.get("total_efectivo_esperado", Decimal("0.00"))
        self.diferencia = monto_fisico - esperado

        if self.diferencia == Decimal("0.00"):
            self.badge_dif.setText("✓  Caja Cuadrada Exacta (Diferencia: Bs 0.00)")
            self.badge_dif.setStyleSheet(f"""
                background: rgba(34, 197, 94, 0.2);
                color: {PALETTE['success']};
                border: 1.5px solid {PALETTE['success']};
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            """)
        elif self.diferencia > 0:
            self.badge_dif.setText(f"▲  Sobrante en Caja: +Bs {self.diferencia:.2f}")
            self.badge_dif.setStyleSheet(f"""
                background: rgba(79, 142, 247, 0.2);
                color: {PALETTE['accent_hover']};
                border: 1.5px solid {PALETTE['accent']};
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            """)
        else:
            self.badge_dif.setText(f"▼  Faltante en Caja: -Bs {abs(self.diferencia):.2f}")
            self.badge_dif.setStyleSheet(f"""
                background: rgba(239, 68, 68, 0.2);
                color: {PALETTE['danger']};
                border: 1.5px solid {PALETTE['danger']};
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            """)

    def _imprimir_arqueo(self):
        """Genera y abre el ticket de arqueo en PDF."""
        try:
            with get_session() as session:
                pdf_path = generar_ticket_arqueo_pdf(session, self.sesion_caja_id)

            if pdf_path and Path(pdf_path).exists():
                try:
                    os.startfile(str(pdf_path))
                except Exception:
                    QMessageBox.information(self, "Ticket Generado", f"Archivo generado en:\n{pdf_path}")
            else:
                QMessageBox.warning(self, "Aviso", "No se pudo generar el archivo de ticket.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al generar reporte de arqueo:\n{e}")

    def _confirmar_cierre(self):
        """Pide confirmación visual amigable y cierra la sesión de caja."""
        txt_fisico = self.input_fisico.text().strip().replace(",", ".")
        try:
            monto_fisico = Decimal(txt_fisico) if txt_fisico else Decimal("0.00")
        except Exception:
            monto_fisico = Decimal("0.00")

        esperado = self.resumen.get("total_efectivo_esperado", Decimal("0.00"))
        cajero = self.resumen.get("usuario_nombre", "Cajero")
        turno = self.resumen.get("turno", "General")

        confirm_dlg = ConfirmarCierreDialog(
            sesion_id=self.sesion_caja_id,
            cajero=cajero,
            turno=turno,
            esperado=esperado,
            fisico=monto_fisico,
            diferencia=self.diferencia,
            estado_arqueo_txt=self.badge_dif.text().strip(),
            parent=self,
        )

        if confirm_dlg.exec() != QDialog.Accepted:
            return

        obs = self.input_obs.text().strip() or None

        try:
            with get_session() as session:
                cerrar_caja(session, self.sesion_caja_id, monto_fisico, obs)
                pdf_path = generar_ticket_arqueo_pdf(session, self.sesion_caja_id)

            self.cierre_completado = True

            # Abrir comprobante
            if pdf_path and Path(pdf_path).exists():
                try:
                    os.startfile(str(pdf_path))
                except Exception:
                    pass

            QMessageBox.information(
                self,
                "Caja Cerrada con Éxito",
                f"✓ La sesión de caja #{self.sesion_caja_id} ha sido cerrada correctamente.\n\n"
                f"• Cajero: {cajero}\n"
                f"• Turno: {turno}\n"
                f"• Efectivo Registrado: {CURRENCY} {monto_fisico:.2f}\n"
                f"• Comprobante de arqueo generado exitosamente."
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error al Cerrar Caja", f"No se pudo cerrar la caja:\n{e}")

