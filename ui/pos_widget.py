"""
ui/pos_widget.py – Pantalla principal del Punto de Venta (POS).

Atajos de teclado:
  Enter  → agregar producto por código de barras (o formato 3*codigo)
  F12    → abrir cobro
  Esc    → cancelar / limpiar venta actual
  F11    → abrir búsqueda de producto por nombre o código
  Del    → eliminar ítem seleccionado en la tabla
"""
from __future__ import annotations

import os
import time
from decimal import Decimal
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QModelIndex, QSize, QEvent, QPoint
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QComboBox,
    QMessageBox, QDialog, QListWidget,
    QListWidgetItem, QAbstractItemView, QSizePolicy,
    QCompleter, QShortcut, QCheckBox, QFileDialog, QScrollArea,
    QProgressBar, QApplication, QGraphicsDropShadowEffect,
)
from PyQt5.QtGui import QKeySequence, QFont, QColor, QStandardItemModel, QStandardItem, QPixmap, QIcon, QPainter, QBrush

from database import SessionLocal, get_session
from models.producto import Producto
from models.cliente import Cliente
from models.usuario import Usuario
from models.caja import SesionCaja
from services.venta_service import registrar_venta, StockInsuficienteError
from services.ticket_service import generar_ticket_pdf
from services.caja_service import obtener_caja_activa
from services.archivo_service import resolver_ruta, guardar_comprobante_pago, guardar_qr_usuario
from services.qr_service import generar_pixmap_qr_dinamico, generar_qr_pil
from ui.caja_dialog import AperturaCajaDialog, CierreCajaDialog
from ui.qr_dialog import GestionQRDialog, VisualizadorImagenDialog
from config import CURRENCY, APP_NAME, QR_DIR
from ui.styles import PALETTE
from services.barcode_service import normalizar_codigo_barras


# ── Constantes de columnas de la tabla de venta ──────────────────────────────
COL_NUM         = 0
COL_CODIGO      = 1
COL_DESCRIPCION = 2
COL_UM          = 3
COL_CANTIDAD    = 4
COL_PRECIO      = 5
COL_SUBTOTAL    = 6
COL_ACCIONES    = 7


# ══════════════════════════════════════════════════════════════════════════════
#  DIÁLOGO DE BÚSQUEDA RÁPIDA DE PRODUCTOS
# ══════════════════════════════════════════════════════════════════════════════

class BuscarProductoDialog(QDialog):
    """Diálogo emergente para buscar productos por nombre o código."""

    producto_seleccionado = pyqtSignal(object)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("🔍 Buscar Producto – Mini Market")
        self.setMinimumSize(640, 460)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(18, 18, 18, 18)

        lbl = QLabel("🔍  Búsqueda rápida de productos")
        lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {PALETTE['accent']};")
        lay.addWidget(lbl)

        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText("Escriba descripción o código de barras (Presione ↓ para bajar a la lista)...")
        self.input_buscar.setStyleSheet(f"""
            QLineEdit {{
                font-size: 14px;
                padding: 8px 12px;
                border: 2px solid {PALETTE['accent']};
                border-radius: 8px;
            }}
        """)
        self.input_buscar.textChanged.connect(self._filtrar)
        self.input_buscar.returnPressed.connect(self._on_enter_pressed)
        lay.addWidget(self.input_buscar)

        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["Código", "Descripción", "Stock", f"Precio ({CURRENCY})"])
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.doubleClicked.connect(self._seleccionar)
        lay.addWidget(self.tabla)

        # Botones de pie
        btn_box = QHBoxLayout()
        lbl_hint = QLabel("💡 Tip: Flecha Abajo (↓) para navegar, Enter para seleccionar, Esc para cerrar")
        lbl_hint.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px;")
        btn_box.addWidget(lbl_hint)
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_sel = QPushButton("✓ Seleccionar")
        btn_sel.setObjectName("btn_primary")
        btn_sel.clicked.connect(self._seleccionar)
        btn_box.addWidget(btn_sel)
        lay.addLayout(btn_box)

        self._cargar_todos()
        self.input_buscar.setFocus()

    def _cargar_todos(self):
        productos = self.session.query(Producto).filter_by(activo=True).all()
        self._llenar_tabla(productos)

    def _filtrar(self, texto: str):
        texto = texto.strip().lower()
        if not texto:
            self._cargar_todos()
            return
        productos = self.session.query(Producto).filter(Producto.activo == True).all()
        filtrados = [
            p for p in productos
            if texto in p.descripcion.lower() or texto in p.codigo_barras.lower()
        ]
        self._llenar_tabla(filtrados)

    def _llenar_tabla(self, productos: list):
        self.tabla.setRowCount(len(productos))
        for i, p in enumerate(productos):
            self.tabla.setItem(i, 0, QTableWidgetItem(p.codigo_barras))
            self.tabla.setItem(i, 1, QTableWidgetItem(p.descripcion))

            st = p.stock_actual
            st_txt = str(int(st)) if st == int(st) else f"{st:.3f}".rstrip('0').rstrip('.')
            if st <= Decimal("0"):
                stock_it = QTableWidgetItem(f"🔴 AGOTADO (0 {p.unidad_medida})")
                stock_it.setForeground(QColor(PALETTE["danger"]))
            elif p.stock_bajo:
                stock_it = QTableWidgetItem(f"🟡 BAJO ({st_txt} {p.unidad_medida})")
                stock_it.setForeground(QColor(PALETTE["warning"]))
            else:
                stock_it = QTableWidgetItem(f"🟢 {st_txt} {p.unidad_medida}")
                stock_it.setForeground(QColor(PALETTE["success"]))
            self.tabla.setItem(i, 2, stock_it)

            precio_it = QTableWidgetItem(f"{p.precio_venta_bs:.2f}")
            precio_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla.setItem(i, 3, precio_it)

            self.tabla.item(i, 0).setData(Qt.UserRole, p)

        if productos:
            self.tabla.selectRow(0)

    def _on_enter_pressed(self):
        if self.tabla.rowCount() > 0:
            self._seleccionar()

    def _seleccionar(self):
        row = self.tabla.currentRow()
        if row < 0 and self.tabla.rowCount() > 0:
            row = 0
        if row < 0:
            return
        prod = self.tabla.item(row, 0).data(Qt.UserRole)
        if prod:
            self.producto_seleccionado.emit(prod)
            self.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Down and self.input_buscar.hasFocus():
            self.tabla.setFocus()
            if self.tabla.rowCount() > 0:
                self.tabla.selectRow(0)
            return
        elif event.key() == Qt.Key_Return and self.tabla.hasFocus():
            self._seleccionar()
            return
        super().keyPressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  DIÁLOGO DE COBRO PROFESIONAL (ESTILO CAJA REGISTRADORA)
# ══════════════════════════════════════════════════════════════════════════════

class CobrarDialog(QDialog):
    """
    Pantalla de cobro modal estilo caja registradora.
    Permite seleccionar Efectivo, QR, Tarjeta o Pago Mixto (QR + Efectivo),
    ingresar montos recibidos y calcular el vuelto en tiempo real.
    """

    def __init__(self, total: Decimal, session, items, usuario, cliente, sesion_caja_id: int | None = None, parent=None):
        super().__init__(parent)
        self.total = total
        self.session = session
        self.items = items
        self.usuario = usuario
        self.usuario_id = usuario.id if usuario else None
        self.usuario_username = getattr(usuario, "username", "cajero") if usuario else "cajero"
        self.usuario_nombre_completo = getattr(usuario, "nombre_completo", self.usuario_username) if usuario else "Cajero"
        self.cliente = cliente
        self.cliente_id = cliente.id if cliente else None
        self.sesion_caja_id = sesion_caja_id
        self.vuelto = Decimal("0.00")
        self.monto_recibido = Decimal("0.00")
        self.monto_qr = Decimal("0.00")
        self.monto_efectivo = Decimal("0.00")
        self.efectivo_recibido = Decimal("0.00")
        self.metodo_pago = "efectivo"
        self.venta_registrada = None
        self.pdf_path = None
        self._comprobante_temp_path: str | None = None
        self._mixto_comprobante_temp_path: str | None = None
        self._modo_qr = "personal"
        self._qr_verificado = False
        self._codigo_referencia_generado = f"OP-{int(time.time()) % 1000000:06d}"
        self._timer_checking = QTimer(self)
        self._timer_checking.setSingleShot(True)
        self._timer_checking.timeout.connect(self._finalizar_checking_animacion)

        self.setWindowTitle("💳  Cobro de Venta – Mini Market")
        self.setFixedSize(800, 580)
        self.setModal(True)
        self._build_ui()

    def showEvent(self, event):
        super().showEvent(event)
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.x() + (screen.width() - self.width()) // 2
            y = screen.y() + (screen.height() - self.height()) // 2
            self.move(max(10, x), max(10, y))
        except Exception:
            pass

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Cabecera: TOTAL A COBRAR ──────────────────────────────────────────
        header = QFrame()
        header.setObjectName("cobrar_header")
        header.setStyleSheet(f"""
            QFrame#cobrar_header {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0f172a, stop:1 {PALETTE['bg_card']});
                border: none;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        hdr_lay = QVBoxLayout(header)
        hdr_lay.setContentsMargins(20, 8, 20, 6)
        hdr_lay.setSpacing(2)

        lbl_th = QLabel("TOTAL A COBRAR")
        lbl_th.setAlignment(Qt.AlignCenter)
        lbl_th.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px; font-weight: bold; letter-spacing: 2px;")
        hdr_lay.addWidget(lbl_th)

        self.lbl_total_grande = QLabel(f"{CURRENCY} {self.total:.2f}")
        self.lbl_total_grande.setAlignment(Qt.AlignCenter)
        self.lbl_total_grande.setStyleSheet(f"""
            font-size: 38px;
            font-weight: 900;
            color: {PALETTE['success']};
            letter-spacing: -1px;
        """)
        hdr_lay.addWidget(self.lbl_total_grande)

        cli_nombre = self.cliente.razon_social if self.cliente else "Público General"
        lbl_cli = QLabel(f"👤  Cliente: {cli_nombre}")
        lbl_cli.setAlignment(Qt.AlignCenter)
        lbl_cli.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px;")
        hdr_lay.addWidget(lbl_cli)

        root.addWidget(header)

        # ── Cuerpo: Métodos de Pago y Paneles ─────────────────────────────────
        body = QWidget()
        body.setStyleSheet(f"background: {PALETTE['bg_base']};")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(20, 8, 20, 8)
        body_lay.setSpacing(8)

        # Selector de Método de Pago (4 opciones)
        lbl_mp = QLabel("SELECCIONE MÉTODO DE PAGO:")
        lbl_mp.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px; font-weight: bold; letter-spacing: 1px;")
        body_lay.addWidget(lbl_mp)

        btns_pago = QHBoxLayout()
        btns_pago.setSpacing(8)
        self._btn_pago = {}
        metodos = [
            ("💵", "efectivo", "Efectivo"),
            ("📱", "QR", "QR Simple"),
            ("💳", "tarjeta", "Tarjeta"),
            ("🔄", "mixto", "Mixto (QR+Efec)"),
        ]
        for icon, m_id, label in metodos:
            btn = QPushButton(f"{icon}  {label}")
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.setStyleSheet(self._estilo_btn_pago(False))
            btn.clicked.connect(lambda _, m=m_id: self._seleccionar_metodo(m))
            btns_pago.addWidget(btn)
            self._btn_pago[m_id] = btn
        body_lay.addLayout(btns_pago)

        # Activar efectivo por defecto
        self._btn_pago["efectivo"].setChecked(True)
        self._btn_pago["efectivo"].setStyleSheet(self._estilo_btn_pago(True))
        self._btn_pago["efectivo"].setStyleSheet(self._estilo_btn_pago(True))

        # ── PANEL 1: Efectivo Completo (Billetes rápidos + Monto + Cambio) ────
        self.frame_efectivo = QFrame()
        self.frame_efectivo.setObjectName("frame_efectivo")
        self.frame_efectivo.setStyleSheet(f"""
            QFrame#frame_efectivo {{
                background: {PALETTE['bg_card']};
                border: none;
                border-radius: 14px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        ef_lay = QVBoxLayout(self.frame_efectivo)
        ef_lay.setContentsMargins(18, 16, 18, 16)
        ef_lay.setSpacing(12)

        lbl_rec = QLabel("MONTO RECIBIDO DEL CLIENTE:")
        lbl_rec.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 14px; font-weight: bold; letter-spacing: 1px;")
        ef_lay.addWidget(lbl_rec)

        self.input_monto = QLineEdit()
        self.input_monto.setPlaceholderText("0.00")
        self.input_monto.setAlignment(Qt.AlignRight)
        self.input_monto.setStyleSheet(f"""
            QLineEdit {{
                font-size: 32px;
                font-weight: bold;
                color: {PALETTE['white']};
                background: {PALETTE['bg_input']};
                border: 2px solid {PALETTE['border']};
                border-radius: 10px;
                padding: 6px 16px;
            }}
            QLineEdit:focus {{
                border-color: {PALETTE['accent']};
                background: {PALETTE['bg_hover']};
            }}
        """)
        self.input_monto.textChanged.connect(self._actualizar_vuelto)
        self.input_monto.returnPressed.connect(self._on_enter_monto)
        ef_lay.addWidget(self.input_monto)

        billetes_lay = QGridLayout()
        billetes_lay.setSpacing(8)
        billetes = [10, 20, 50, 100, 200]
        for idx, valor in enumerate(billetes):
            b_btn = QPushButton(f"Bs {valor}")
            b_btn.setFixedHeight(38)
            b_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {PALETTE['bg_hover']};
                    color: {PALETTE['accent']};
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background: {PALETTE['accent']}; color: white; }}
            """)
            b_btn.clicked.connect(lambda _, v=valor: self._agregar_billete(v))
            billetes_lay.addWidget(b_btn, 0, idx)

        btn_exacto = QPushButton("💰 Monto Exacto")
        btn_exacto.setFixedHeight(38)
        btn_exacto.setStyleSheet(f"""
            QPushButton {{
                background: rgba(34, 197, 94, 0.18);
                color: {PALETTE['success']};
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {PALETTE['success']}; color: white; }}
        """)
        btn_exacto.clicked.connect(self._monto_exacto)
        billetes_lay.addWidget(btn_exacto, 1, 0, 1, 3)

        btn_borrar = QPushButton("⌫ Borrar")
        btn_borrar.setFixedHeight(38)
        btn_borrar.setStyleSheet(f"""
            QPushButton {{
                background: rgba(239, 68, 68, 0.18);
                color: {PALETTE['danger']};
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {PALETTE['danger']}; color: white; }}
        """)
        btn_borrar.clicked.connect(lambda: self.input_monto.clear())
        billetes_lay.addWidget(btn_borrar, 1, 3, 1, 2)
        ef_lay.addLayout(billetes_lay)

        vuelto_card = QFrame()
        vuelto_card.setObjectName("vuelto_card")
        vuelto_card.setStyleSheet("""
            QFrame#vuelto_card {
                background: rgba(15, 23, 42, 0.7);
                border: none;
                border-radius: 10px;
                padding: 6px 14px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        vuelto_card_lay = QHBoxLayout(vuelto_card)
        vuelto_card_lay.setContentsMargins(12, 8, 12, 8)

        lbl_v_title = QLabel("CAMBIO / VUELTO:")
        lbl_v_title.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 14px; font-weight: bold;")
        vuelto_card_lay.addWidget(lbl_v_title)
        vuelto_card_lay.addStretch()

        self.lbl_vuelto = QLabel("—")
        self.lbl_vuelto.setStyleSheet(f"font-size: 30px; font-weight: 900; color: {PALETTE['text_muted']}; border: none;")
        vuelto_card_lay.addWidget(self.lbl_vuelto)
        ef_lay.addWidget(vuelto_card)

        body_lay.addWidget(self.frame_efectivo)

        # ── PANEL 2: Pago Mixto (QR + Efectivo en 2 Columnas) ─────────────────
        self.frame_mixto = QFrame()
        self.frame_mixto.setObjectName("frame_mixto")
        self.frame_mixto.setStyleSheet(f"""
            QFrame#frame_mixto {{
                background: {PALETTE['bg_card']};
                border: none;
                border-radius: 14px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        mx_lay = QHBoxLayout(self.frame_mixto)
        mx_lay.setContentsMargins(14, 10, 14, 10)
        mx_lay.setSpacing(14)

        # ── COLUMNA IZQUIERDA: 1. PAGO POR QR ─────────────────────────────────
        col_qr = QFrame()
        col_qr.setStyleSheet(f"""
            QFrame {{
                background: rgba(15, 23, 42, 0.45);
                border: 1px solid {PALETTE['border']};
                border-radius: 10px;
            }}
        """)
        col_qr_lay = QVBoxLayout(col_qr)
        col_qr_lay.setContentsMargins(12, 10, 12, 10)
        col_qr_lay.setSpacing(8)

        lbl_mx_qr_tit = QLabel("1. MONTO A PAGAR POR QR (📱):")
        lbl_mx_qr_tit.setStyleSheet(f"color: {PALETTE['accent']}; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
        col_qr_lay.addWidget(lbl_mx_qr_tit)

        self.input_mixto_qr = QLineEdit()
        self.input_mixto_qr.setPlaceholderText("0.00")
        self.input_mixto_qr.setAlignment(Qt.AlignRight)
        self.input_mixto_qr.setStyleSheet(f"""
            QLineEdit {{
                font-size: 22px;
                font-weight: bold;
                color: {PALETTE['white']};
                background: {PALETTE['bg_input']};
                border: 2px solid {PALETTE['accent']};
                border-radius: 8px;
                padding: 4px 10px;
            }}
        """)
        self.input_mixto_qr.textChanged.connect(self._actualizar_mixto)
        self.input_mixto_qr.returnPressed.connect(lambda: self.input_mixto_efectivo.setFocus())
        col_qr_lay.addWidget(self.input_mixto_qr)

        # Botones rápidos QR
        qr_btns_lay = QHBoxLayout()
        qr_btns_lay.setSpacing(6)
        btn_qr_mitad = QPushButton(f"½ Mitad ({CURRENCY} {self.total / 2:.2f})")
        btn_qr_mitad.setFixedHeight(30)
        btn_qr_mitad.setStyleSheet(self._estilo_btn_rapido())
        btn_qr_mitad.clicked.connect(lambda: self.input_mixto_qr.setText(f"{self.total / 2:.2f}"))
        qr_btns_lay.addWidget(btn_qr_mitad)

        btn_qr_total = QPushButton("Total QR")
        btn_qr_total.setFixedHeight(30)
        btn_qr_total.setStyleSheet(self._estilo_btn_rapido())
        btn_qr_total.clicked.connect(lambda: self.input_mixto_qr.setText(f"{self.total:.2f}"))
        qr_btns_lay.addWidget(btn_qr_total)

        btn_qr_clear = QPushButton("⌫")
        btn_qr_clear.setFixedSize(30, 30)
        btn_qr_clear.setStyleSheet(self._estilo_btn_borrar())
        btn_qr_clear.clicked.connect(lambda: self.input_mixto_qr.clear())
        qr_btns_lay.addWidget(btn_qr_clear)
        col_qr_lay.addLayout(qr_btns_lay)

        # Confirmación QR dentro de Pago Mixto
        self.mixto_qr_box = QFrame()
        self.mixto_qr_box.setStyleSheet("""
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid #334155;
            border-radius: 8px;
        """)
        mqr_lay = QVBoxLayout(self.mixto_qr_box)
        mqr_lay.setContentsMargins(8, 6, 8, 6)
        mqr_lay.setSpacing(6)

        mqr_top = QHBoxLayout()
        self.chk_mixto_qr_confirmado = QCheckBox("✓ Confirmar recepción QR")
        self.chk_mixto_qr_confirmado.setCursor(Qt.PointingHandCursor)
        self.chk_mixto_qr_confirmado.setStyleSheet(f"""
            QCheckBox {{
                font-size: 12px;
                font-weight: bold;
                color: {PALETTE['accent']};
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid {PALETTE['accent']};
                border-radius: 4px;
                background: {PALETTE['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {PALETTE['success']};
                border-color: {PALETTE['success']};
            }}
        """)
        self.chk_mixto_qr_confirmado.toggled.connect(self._actualizar_mixto)
        mqr_top.addWidget(self.chk_mixto_qr_confirmado)
        mqr_top.addStretch()

        btn_ver_qr = QPushButton("👁 Ver QR")
        btn_ver_qr.setFixedHeight(24)
        btn_ver_qr.setCursor(Qt.PointingHandCursor)
        btn_ver_qr.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['bg_hover']};
                color: {PALETTE['text_secondary']};
                border: 1px solid {PALETTE['border']};
                border-radius: 4px;
                font-size: 11px;
                padding: 0 6px;
            }}
            QPushButton:hover {{ color: white; background: {PALETTE['accent']}; }}
        """)
        btn_ver_qr.clicked.connect(self._mostrar_qr_popup)
        mqr_top.addWidget(btn_ver_qr)
        mqr_lay.addLayout(mqr_top)

        mqr_ref_lay = QHBoxLayout()
        mqr_ref_lay.setSpacing(6)
        self.input_mixto_ref_qr = QLineEdit()
        self.input_mixto_ref_qr.setPlaceholderText("N° Ref. QR (Opcional)")
        self.input_mixto_ref_qr.setFixedHeight(26)
        self.input_mixto_ref_qr.setStyleSheet(f"""
            QLineEdit {{
                background: {PALETTE['bg_input']};
                border: 1px solid {PALETTE['border']};
                border-radius: 4px;
                color: {PALETTE['white']};
                font-size: 11px;
                padding: 2px 6px;
            }}
        """)
        mqr_ref_lay.addWidget(self.input_mixto_ref_qr, 1)

        self.btn_mixto_adjuntar = QPushButton("📎 Comprobante")
        self.btn_mixto_adjuntar.setFixedHeight(26)
        self.btn_mixto_adjuntar.setCursor(Qt.PointingHandCursor)
        self.btn_mixto_adjuntar.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['bg_hover']};
                color: {PALETTE['text_primary']};
                border: 1px solid {PALETTE['border']};
                border-radius: 4px;
                font-size: 11px;
                padding: 0 6px;
            }}
        """)
        self.btn_mixto_adjuntar.clicked.connect(self._adjuntar_comprobante_mixto)
        mqr_ref_lay.addWidget(self.btn_mixto_adjuntar)
        mqr_lay.addLayout(mqr_ref_lay)

        self.lbl_mixto_adjunto = QLabel("")
        self.lbl_mixto_adjunto.setStyleSheet("color: #4ade80; font-size: 11px;")
        self.lbl_mixto_adjunto.hide()
        mqr_lay.addWidget(self.lbl_mixto_adjunto)

        col_qr_lay.addWidget(self.mixto_qr_box)
        col_qr_lay.addStretch()
        mx_lay.addWidget(col_qr, 1)

        # ── COLUMNA DERECHA: 2. PAGO EN EFECTIVO ──────────────────────────────
        col_ef = QFrame()
        col_ef.setStyleSheet(f"""
            QFrame {{
                background: rgba(15, 23, 42, 0.45);
                border: 1px solid {PALETTE['border']};
                border-radius: 10px;
            }}
        """)
        col_ef_lay = QVBoxLayout(col_ef)
        col_ef_lay.setContentsMargins(12, 10, 12, 10)
        col_ef_lay.setSpacing(8)

        ef_top_row = QHBoxLayout()
        lbl_mx_ef_tit = QLabel("2. EFECTIVO (💵):")
        lbl_mx_ef_tit.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
        ef_top_row.addWidget(lbl_mx_ef_tit)
        ef_top_row.addStretch()

        self.lbl_restante_efec = QLabel(f"Resta: {CURRENCY} {self.total:.2f}")
        self.lbl_restante_efec.setStyleSheet(f"color: {PALETTE['warning']}; font-size: 13px; font-weight: bold;")
        ef_top_row.addWidget(self.lbl_restante_efec)
        col_ef_lay.addLayout(ef_top_row)

        self.input_mixto_efectivo = QLineEdit()
        self.input_mixto_efectivo.setPlaceholderText("0.00")
        self.input_mixto_efectivo.setAlignment(Qt.AlignRight)
        self.input_mixto_efectivo.setStyleSheet(f"""
            QLineEdit {{
                font-size: 22px;
                font-weight: bold;
                color: {PALETTE['white']};
                background: {PALETTE['bg_input']};
                border: 2px solid {PALETTE['border']};
                border-radius: 8px;
                padding: 4px 10px;
            }}
            QLineEdit:focus {{
                border-color: {PALETTE['success']};
            }}
        """)
        self.input_mixto_efectivo.textChanged.connect(self._actualizar_mixto)
        self.input_mixto_efectivo.returnPressed.connect(self._on_enter_mixto_efectivo)
        col_ef_lay.addWidget(self.input_mixto_efectivo)

        # Botones rápidos de efectivo
        ef_grid = QGridLayout()
        ef_grid.setSpacing(4)
        btn_ef_exacto = QPushButton("💰 Exacto Restante")
        btn_ef_exacto.setFixedHeight(28)
        btn_ef_exacto.setStyleSheet(self._estilo_btn_exacto())
        btn_ef_exacto.clicked.connect(self._mixto_efectivo_exacto)
        ef_grid.addWidget(btn_ef_exacto, 0, 0, 1, 4)

        btn_ef_clear = QPushButton("⌫")
        btn_ef_clear.setFixedHeight(28)
        btn_ef_clear.setStyleSheet(self._estilo_btn_borrar())
        btn_ef_clear.clicked.connect(lambda: self.input_mixto_efectivo.clear())
        ef_grid.addWidget(btn_ef_clear, 0, 4)

        for col_i, v in enumerate([10, 20, 50, 100, 200]):
            b = QPushButton(f"Bs {v}")
            b.setFixedHeight(26)
            b.setStyleSheet(self._estilo_btn_rapido())
            b.clicked.connect(lambda _, val=v: self.input_mixto_efectivo.setText(f"{val:.2f}"))
            ef_grid.addWidget(b, 1, col_i)
        col_ef_lay.addLayout(ef_grid)

        # Tarjeta de Vuelto
        mx_vuelto_card = QFrame()
        mx_vuelto_card.setObjectName("mx_vuelto_card")
        mx_vuelto_card.setStyleSheet("""
            QFrame#mx_vuelto_card {
                background: rgba(15, 23, 42, 0.7);
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 4px 10px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        mx_v_lay = QHBoxLayout(mx_vuelto_card)
        mx_v_lay.setContentsMargins(10, 6, 10, 6)

        lbl_mx_v_title = QLabel("CAMBIO / VUELTO:")
        lbl_mx_v_title.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px; font-weight: bold;")
        mx_v_lay.addWidget(lbl_mx_v_title)
        mx_v_lay.addStretch()

        self.lbl_mixto_vuelto = QLabel("—")
        self.lbl_mixto_vuelto.setStyleSheet(f"font-size: 24px; font-weight: 900; color: {PALETTE['text_muted']}; border: none;")
        mx_v_lay.addWidget(self.lbl_mixto_vuelto)
        col_ef_lay.addWidget(mx_vuelto_card)
        col_ef_lay.addStretch()

        mx_lay.addWidget(col_ef, 1)

        self.frame_mixto.hide()
        body_lay.addWidget(self.frame_mixto)

        # ── PANEL 3: QR Simple (Imagen QR del Cajero + Confirmación) ─────────
        self.frame_qr = QFrame()
        self.frame_qr.setObjectName("frame_qr")
        self.frame_qr.setStyleSheet(f"""
            QFrame#frame_qr {{
                background: {PALETTE['bg_card']};
                border: 1px solid {PALETTE['border']};
                border-radius: 12px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        qr_lay = QHBoxLayout(self.frame_qr)
        qr_lay.setContentsMargins(14, 12, 14, 12)
        qr_lay.setSpacing(14)

        # ── COLUMNA IZQUIERDA: Código QR Subido por el Cajero ──
        qr_col_izq = QVBoxLayout()
        qr_col_izq.setSpacing(6)
        qr_col_izq.setAlignment(Qt.AlignCenter)

        # Caja blanca limpia para mostrar el QR subido (250x250)
        self.qr_box = QFrame()
        self.qr_box.setFixedSize(250, 250)
        self.qr_box.setCursor(Qt.PointingHandCursor)
        self.qr_box.setToolTip("🔍 Haz clic para ver en pantalla completa")
        self.qr_box.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 2px solid #3b82f6;
                border-radius: 12px;
            }
            QFrame:hover {
                border-color: #60a5fa;
            }
        """)
        qr_box_lay = QVBoxLayout(self.qr_box)
        qr_box_lay.setContentsMargins(4, 4, 4, 4)
        qr_box_lay.setAlignment(Qt.AlignCenter)

        # Label para mostrar la imagen del QR subida por el cajero
        self.lbl_qr_img = QLabel()
        self.lbl_qr_img.setAlignment(Qt.AlignCenter)
        self.lbl_qr_img.setFixedSize(240, 240)
        self.lbl_qr_img.setCursor(Qt.PointingHandCursor)
        self.lbl_qr_img.setToolTip("🔍 Haz clic para ver en pantalla completa")
        self.lbl_qr_img.setStyleSheet("background: transparent; border: none;")
        self.lbl_qr_img.mousePressEvent = lambda e: self._mostrar_qr_popup()
        self.qr_box.mousePressEvent = lambda e: self._mostrar_qr_popup()
        qr_box_lay.addWidget(self.lbl_qr_img)

        # Panel cuando aún no ha subido su QR
        self.frame_sin_qr = QWidget()
        sin_qr_lay = QVBoxLayout(self.frame_sin_qr)
        sin_qr_lay.setContentsMargins(4, 4, 4, 4)
        sin_qr_lay.setAlignment(Qt.AlignCenter)
        sin_qr_lay.setSpacing(6)

        lbl_no_qr_ico = QLabel("📱")
        lbl_no_qr_ico.setStyleSheet("font-size: 34px; border: none;")
        lbl_no_qr_ico.setAlignment(Qt.AlignCenter)
        sin_qr_lay.addWidget(lbl_no_qr_ico)

        lbl_no_qr_txt = QLabel("Sin QR configurado")
        lbl_no_qr_txt.setStyleSheet("color: #475569; font-size: 13px; font-weight: bold; border: none;")
        lbl_no_qr_txt.setAlignment(Qt.AlignCenter)
        sin_qr_lay.addWidget(lbl_no_qr_txt)

        btn_subir_ahora = QPushButton("📤 Subir Mi QR")
        btn_subir_ahora.setFixedHeight(28)
        btn_subir_ahora.setCursor(Qt.PointingHandCursor)
        btn_subir_ahora.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['accent']};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
                padding: 0 10px;
            }}
            QPushButton:hover {{ background: {PALETTE['accent_hover']}; }}
        """)
        btn_subir_ahora.clicked.connect(self._abrir_gestion_qr_cajero)
        sin_qr_lay.addWidget(btn_subir_ahora)
        self.frame_sin_qr.hide()
        qr_box_lay.addWidget(self.frame_sin_qr)

        qr_col_izq.addWidget(self.qr_box, alignment=Qt.AlignCenter)

        # Botones de acción bajo el QR
        qr_btns_row = QHBoxLayout()
        qr_btns_row.setSpacing(6)

        self.btn_qr_zoom = QPushButton("🔍 Ampliar")
        self.btn_qr_zoom.setFixedHeight(28)
        self.btn_qr_zoom.setCursor(Qt.PointingHandCursor)
        self.btn_qr_zoom.setStyleSheet(f"""
            QPushButton {{
                background: rgba(59, 130, 246, 0.15);
                color: {PALETTE['accent']};
                border: 1px solid {PALETTE['accent']};
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                background: {PALETTE['accent']};
                color: #ffffff;
            }}
        """)
        self.btn_qr_zoom.clicked.connect(self._mostrar_qr_popup)
        qr_btns_row.addWidget(self.btn_qr_zoom)

        self.btn_qr_cambiar = QPushButton("🔄 Cambiar QR")
        self.btn_qr_cambiar.setFixedHeight(28)
        self.btn_qr_cambiar.setCursor(Qt.PointingHandCursor)
        self.btn_qr_cambiar.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['bg_hover']};
                color: {PALETTE['text_secondary']};
                border: 1px solid {PALETTE['border']};
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                background: {PALETTE['bg_card']};
                color: #ffffff;
            }}
        """)
        self.btn_qr_cambiar.clicked.connect(self._abrir_gestion_qr_cajero)
        qr_btns_row.addWidget(self.btn_qr_cambiar)

        qr_col_izq.addLayout(qr_btns_row)
        qr_lay.addLayout(qr_col_izq)

        # ── COLUMNA DERECHA: Monto exacto, Cajero y Checking de Confirmación ──
        qr_col_der = QVBoxLayout()
        qr_col_der.setSpacing(8)

        # Card de Total a Pagar y Cajero
        monto_info_card = QFrame()
        monto_info_card.setStyleSheet("""
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(59, 130, 246, 0.25);
            border-radius: 10px;
            padding: 2px;
        """)
        mic_lay = QVBoxLayout(monto_info_card)
        mic_lay.setContentsMargins(12, 6, 12, 6)
        mic_lay.setSpacing(2)

        self.lbl_monto_badge_qr = QLabel(f"💵 TOTAL A PAGAR: {CURRENCY} {self.total:.2f}")
        self.lbl_monto_badge_qr.setStyleSheet(f"""
            color: {PALETTE['success']};
            font-size: 17px;
            font-weight: 900;
        """)
        mic_lay.addWidget(self.lbl_monto_badge_qr)

        cajero_nom = self.usuario.nombre_completo if self.usuario else self.usuario_username
        self.lbl_qr_cajero = QLabel(f"👤 Cajero receptor: <b>{cajero_nom}</b>")
        self.lbl_qr_cajero.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px;")
        mic_lay.addWidget(self.lbl_qr_cajero)
        qr_col_der.addWidget(monto_info_card)

        # Card de Checking / Confirmación de Pago
        self.card_confirmacion_qr = QFrame()
        self.card_confirmacion_qr.setObjectName("card_confirmacion_qr")
        self.card_confirmacion_qr.setStyleSheet(f"""
            QFrame#card_confirmacion_qr {{
                background: rgba(30, 41, 59, 0.7);
                border: 2px solid {PALETTE['border']};
                border-radius: 10px;
            }}
        """)
        conf_lay = QVBoxLayout(self.card_confirmacion_qr)
        conf_lay.setContentsMargins(12, 8, 12, 8)
        conf_lay.setSpacing(6)

        self.checking_header_lay = QHBoxLayout()
        self.lbl_checking_icon = QLabel("⏳")
        self.lbl_checking_icon.setStyleSheet("font-size: 18px; background: transparent; border: none;")
        self.checking_header_lay.addWidget(self.lbl_checking_icon)

        self.lbl_checking_titulo = QLabel("ESPERANDO PAGO DEL CLIENTE")
        self.lbl_checking_titulo.setStyleSheet("font-size: 13px; font-weight: 900; color: #38bdf8; background: transparent; border: none;")
        self.checking_header_lay.addWidget(self.lbl_checking_titulo)
        self.checking_header_lay.addStretch()

        self.btn_deshacer_checking = QPushButton("↩ Reintentar")
        self.btn_deshacer_checking.setFixedHeight(22)
        self.btn_deshacer_checking.setCursor(Qt.PointingHandCursor)
        self.btn_deshacer_checking.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {PALETTE['text_muted']};
                border: 1px solid {PALETTE['border']};
                border-radius: 4px;
                font-size: 11px;
                padding: 0 6px;
            }}
            QPushButton:hover {{ color: {PALETTE['white']}; border-color: {PALETTE['white']}; }}
        """)
        self.btn_deshacer_checking.clicked.connect(self._reiniciar_checking)
        self.btn_deshacer_checking.hide()
        self.checking_header_lay.addWidget(self.btn_deshacer_checking)
        conf_lay.addLayout(self.checking_header_lay)

        self.lbl_checking_detalle = QLabel(f"Pida al cliente escanear el QR y transferir {CURRENCY} {self.total:.2f}:")
        self.lbl_checking_detalle.setWordWrap(True)
        self.lbl_checking_detalle.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 11px; background: transparent; border: none;")
        conf_lay.addWidget(self.lbl_checking_detalle)

        self.pbar_checking = QProgressBar()
        self.pbar_checking.setFixedHeight(6)
        self.pbar_checking.setRange(0, 0)
        self.pbar_checking.setTextVisible(False)
        self.pbar_checking.setStyleSheet(f"""
            QProgressBar {{
                background: {PALETTE['bg_input']};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {PALETTE['accent']};
                border-radius: 3px;
            }}
        """)
        self.pbar_checking.hide()
        conf_lay.addWidget(self.pbar_checking)

        # Botón principal de Checking
        self.btn_verificar_checking = QPushButton(f"⚡ Confirmar Pago de {CURRENCY} {self.total:.2f}")
        self.btn_verificar_checking.setFixedHeight(38)
        self.btn_verificar_checking.setCursor(Qt.PointingHandCursor)
        self.btn_verificar_checking.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563eb, stop:1 #1d4ed8);
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 900;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #2563eb);
            }}
        """)
        self.btn_verificar_checking.clicked.connect(self._iniciar_verificacion_checking)
        conf_lay.addWidget(self.btn_verificar_checking)

        self.chk_confirmar_qr = QCheckBox("✓ Marcar manualmente como pago recibido")
        self.chk_confirmar_qr.setCursor(Qt.PointingHandCursor)
        self.chk_confirmar_qr.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px; spacing: 6px;")
        self.chk_confirmar_qr.toggled.connect(self._on_qr_confirmado_toggle)
        conf_lay.addWidget(self.chk_confirmar_qr)

        # Fila de Nro. de Referencia + Adjuntar archivo
        ref_row = QHBoxLayout()
        ref_row.setSpacing(6)

        lbl_ref = QLabel("N° Ref:")
        lbl_ref.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 11px; font-weight: bold;")
        ref_row.addWidget(lbl_ref)

        self.input_ref_qr = QLineEdit()
        self.input_ref_qr.setText(self._codigo_referencia_generado)
        self.input_ref_qr.setFixedHeight(28)
        self.input_ref_qr.setStyleSheet(f"""
            QLineEdit {{
                background: {PALETTE['bg_input']};
                border: 1px solid {PALETTE['border']};
                border-radius: 6px;
                color: {PALETTE['white']};
                font-size: 12px;
                padding: 2px 6px;
            }}
            QLineEdit:focus {{
                border-color: {PALETTE['accent']};
            }}
        """)
        ref_row.addWidget(self.input_ref_qr, 1)

        self.btn_adjuntar_qr = QPushButton("📎 Comprobante")
        self.btn_adjuntar_qr.setFixedHeight(28)
        self.btn_adjuntar_qr.setCursor(Qt.PointingHandCursor)
        self.btn_adjuntar_qr.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['bg_hover']};
                color: {PALETTE['text_primary']};
                border: 1px solid {PALETTE['border']};
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                background: {PALETTE['accent']};
                color: #ffffff;
            }}
        """)
        self.btn_adjuntar_qr.clicked.connect(self._adjuntar_comprobante_qr)
        ref_row.addWidget(self.btn_adjuntar_qr)
        conf_lay.addLayout(ref_row)

        self.lbl_adjunto_estado = QLabel("")
        self.lbl_adjunto_estado.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
        self.lbl_adjunto_estado.hide()
        conf_lay.addWidget(self.lbl_adjunto_estado)

        qr_col_der.addWidget(self.card_confirmacion_qr)
        qr_lay.addLayout(qr_col_der, 1)

        self.frame_qr.hide()
        body_lay.addWidget(self.frame_qr)

        # ── PANEL 4: Tarjeta POS Terminal ────────────────────────────────────
        self.frame_no_efectivo = QFrame()
        self.frame_no_efectivo.setObjectName("frame_no_efectivo")
        self.frame_no_efectivo.setStyleSheet(f"""
            QFrame#frame_no_efectivo {{
                background: {PALETTE['bg_card']};
                border: none;
                border-radius: 14px;
                padding: 24px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        ne_lay = QVBoxLayout(self.frame_no_efectivo)
        ne_lay.setAlignment(Qt.AlignCenter)
        self.lbl_ne_info = QLabel("💳 Pago con Tarjeta de Débito/Crédito.\nProcese el cobro en el POS y confirme la venta.")
        self.lbl_ne_info.setAlignment(Qt.AlignCenter)
        self.lbl_ne_info.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 15px; font-weight: 600;")
        ne_lay.addWidget(self.lbl_ne_info)
        self.frame_no_efectivo.hide()
        body_lay.addWidget(self.frame_no_efectivo)

        # Mensaje de error
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("alert_danger")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.hide()
        body_lay.addWidget(self.lbl_error)

        body_lay.addStretch()

        root.addWidget(body, 1)

        # ── Pie: Botones Cancelar / Confirmar ─────────────────────────────────
        footer = QFrame()
        footer.setObjectName("cobrar_footer")
        footer.setStyleSheet(f"""
            QFrame#cobrar_footer {{
                background: {PALETTE['bg_card']};
                border: none;
            }}
        """)
        ft_lay = QHBoxLayout(footer)
        ft_lay.setContentsMargins(20, 10, 20, 10)
        ft_lay.setSpacing(12)

        btn_cancelar = QPushButton("✗  Cancelar (Esc)")
        btn_cancelar.setFixedHeight(44)
        btn_cancelar.setStyleSheet(f"""
            QPushButton {{
                background: rgba(239, 68, 68, 0.15);
                color: #f87171;
                border: 1px solid {PALETTE['danger']};
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {PALETTE['danger']}; color: white; }}
        """)
        btn_cancelar.clicked.connect(self.reject)
        ft_lay.addWidget(btn_cancelar, 1)

        self.btn_confirmar = QPushButton("✓  Confirmar Cobro  [Enter]")
        self.btn_confirmar.setFixedHeight(44)
        self.btn_confirmar.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['success']};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #16a34a; }}
            QPushButton:pressed {{ background: #15803d; }}
            QPushButton:disabled {{
                background: {PALETTE['bg_surface']};
                color: {PALETTE['text_muted']};
                border: 1px solid {PALETTE['border']};
            }}
        """)
        self.btn_confirmar.clicked.connect(self._confirmar)
        ft_lay.addWidget(self.btn_confirmar, 2)

        root.addWidget(footer)

        # Enfocar el campo de monto al abrir
        QTimer.singleShot(100, self.input_monto.setFocus)

    # ── Helpers de Estilo ─────────────────────────────────────────────────────

    def _estilo_btn_pago(self, activo: bool) -> str:
        if activo:
            return f"""
                QPushButton {{
                    background: {PALETTE['accent']};
                    color: white;
                    border: none;
                    border-radius: 10px;
                    font-size: 14px;
                    font-weight: bold;
                }}
            """
        return f"""
            QPushButton {{
                background: {PALETTE['bg_hover']};
                color: {PALETTE['text_secondary']};
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {PALETTE['bg_card']};
                color: {PALETTE['text_primary']};
            }}
        """

    def _estilo_btn_rapido(self) -> str:
        return f"""
            QPushButton {{
                background: {PALETTE['bg_hover']};
                color: {PALETTE['accent']};
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 4px 10px;
            }}
            QPushButton:hover {{ background: {PALETTE['accent']}; color: white; }}
        """

    def _estilo_btn_exacto(self) -> str:
        return f"""
            QPushButton {{
                background: rgba(34, 197, 94, 0.18);
                color: {PALETTE['success']};
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 4px 12px;
            }}
            QPushButton:hover {{ background: {PALETTE['success']}; color: white; }}
        """

    def _estilo_btn_borrar(self) -> str:
        return f"""
            QPushButton {{
                background: rgba(239, 68, 68, 0.18);
                color: {PALETTE['danger']};
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {PALETTE['danger']}; color: white; }}
        """

    # ── Manejo de Métodos de Pago ─────────────────────────────────────────────

    def _seleccionar_metodo(self, metodo: str):
        self.metodo_pago = metodo
        for m, btn in self._btn_pago.items():
            btn.setChecked(m == metodo)
            btn.setStyleSheet(self._estilo_btn_pago(m == metodo))

        es_efectivo    = (metodo == "efectivo")
        es_qr          = (metodo == "QR")
        es_mixto       = (metodo == "mixto")
        es_tarjeta     = (metodo == "tarjeta")

        self.frame_efectivo.setVisible(es_efectivo)
        self.frame_qr.setVisible(es_qr)
        self.frame_mixto.setVisible(es_mixto)
        self.frame_no_efectivo.setVisible(es_tarjeta)
        self.lbl_error.hide()

        if es_efectivo:
            self._actualizar_vuelto()
            QTimer.singleShot(50, self.input_monto.setFocus)
        elif es_qr:
            self._refrescar_panel_qr()
            self.lbl_vuelto.setText("—")
            self.btn_confirmar.setEnabled(self._qr_verificado or self.chk_confirmar_qr.isChecked())
        elif es_mixto:
            self._actualizar_mixto()
            QTimer.singleShot(50, self.input_mixto_qr.setFocus)
        else:
            self.lbl_vuelto.setText("—")
            self.btn_confirmar.setEnabled(True)

    def _obtener_qr_actual(self) -> str | None:
        if not self.usuario_id:
            return None
        try:
            with get_session() as s:
                u = s.get(Usuario, self.usuario_id)
                if u:
                    return u.qr_imagen
        except Exception:
            pass
        return getattr(self.usuario, "qr_imagen", None)

    def _refrescar_panel_qr(self):
        monto_a_cobrar = self.monto_qr if (self.metodo_pago == "mixto" and self.monto_qr > 0) else self.total
        self.lbl_monto_badge_qr.setText(f"💵 TOTAL A PAGAR: {CURRENCY} {monto_a_cobrar:.2f}")
        cajero_nom = self.usuario.nombre_completo if self.usuario else self.usuario_username
        self.lbl_qr_cajero.setText(f"👤 Cajero receptor: <b>{cajero_nom}</b>")

        if not self._qr_verificado:
            self.btn_verificar_checking.setText(f"⚡ Confirmar Pago de {CURRENCY} {monto_a_cobrar:.2f}")
            self.lbl_checking_detalle.setText(f"Pida al cliente escanear el QR y transferir {CURRENCY} {monto_a_cobrar:.2f}:")

        qr_personal_rel = self._obtener_qr_actual()
        ruta_personal = resolver_ruta(qr_personal_rel) if qr_personal_rel else None

        if ruta_personal and ruta_personal.exists():
            pix = QPixmap(str(ruta_personal))
            if not pix.isNull():
                self.lbl_qr_img.setPixmap(pix.scaled(240, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.lbl_qr_img.show()
                self.frame_sin_qr.hide()
                self.btn_qr_zoom.setEnabled(True)
            else:
                self.lbl_qr_img.hide()
                self.frame_sin_qr.show()
                self.btn_qr_zoom.setEnabled(False)
        else:
            self.lbl_qr_img.hide()
            self.frame_sin_qr.show()
            self.btn_qr_zoom.setEnabled(False)

    def _alternar_modo_qr(self):
        self._refrescar_panel_qr()

    def _iniciar_verificacion_checking(self):
        monto_a_cobrar = self.monto_qr if (self.metodo_pago == "mixto" and self.monto_qr > 0) else self.total
        self.btn_verificar_checking.setEnabled(False)
        self.btn_verificar_checking.setText("⏳ Verificando acreditación de pago...")
        self.lbl_checking_titulo.setText("CONSULTANDO RECEPCIÓN BANCARIA...")
        self.lbl_checking_titulo.setStyleSheet("font-size: 14px; font-weight: 900; color: #f59e0b;")
        self.lbl_checking_icon.setText("🔄")
        self.lbl_checking_detalle.setText(f"Comprobando acreditación de {CURRENCY} {monto_a_cobrar:.2f} en cuenta...")
        self.pbar_checking.show()
        self._timer_checking.start(650)

    def _finalizar_checking_animacion(self):
        monto_a_cobrar = self.monto_qr if (self.metodo_pago == "mixto" and self.monto_qr > 0) else self.total
        self.pbar_checking.hide()
        self._qr_verificado = True
        self.chk_confirmar_qr.blockSignals(True)
        self.chk_confirmar_qr.setChecked(True)
        self.chk_confirmar_qr.blockSignals(False)

        # Estilo CHECKING VERDE
        self.card_confirmacion_qr.setStyleSheet("""
            QFrame#card_confirmacion_qr {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(34, 197, 94, 0.25), stop:1 rgba(21, 128, 61, 0.15));
                border: 2px solid #22c55e;
                border-radius: 10px;
                padding: 8px;
            }
        """)
        self.lbl_checking_icon.setText("✅")
        self.lbl_checking_titulo.setText("¡PAGO VERIFICADO Y RECIBIDO!")
        self.lbl_checking_titulo.setStyleSheet("font-size: 13px; font-weight: 900; color: #22c55e;")

        ref = self.input_ref_qr.text().strip() or self._codigo_referencia_generado
        self.lbl_checking_detalle.setText(
            f"✓ Monto de {CURRENCY} {monto_a_cobrar:.2f} acreditado en cuenta.\n"
            f"Operación Ref: {ref} • Presione [Enter] para finalizar la venta."
        )
        self.lbl_checking_detalle.setStyleSheet("color: #f1f5f9; font-size: 11px; font-weight: 600;")

        self.btn_verificar_checking.hide()
        self.btn_deshacer_checking.show()

        try:
            QApplication.beep()
        except Exception:
            pass

        self.btn_confirmar.setEnabled(True)
        self.btn_confirmar.setFocus()

    def _reiniciar_checking(self):
        monto_a_cobrar = self.monto_qr if (self.metodo_pago == "mixto" and self.monto_qr > 0) else self.total
        self._qr_verificado = False
        self.chk_confirmar_qr.blockSignals(True)
        self.chk_confirmar_qr.setChecked(False)
        self.chk_confirmar_qr.blockSignals(False)

        self.card_confirmacion_qr.setStyleSheet(f"""
            QFrame#card_confirmacion_qr {{
                background: rgba(30, 41, 59, 0.7);
                border: 2px solid {PALETTE['border']};
                border-radius: 10px;
            }}
        """)
        self.lbl_checking_icon.setText("⏳")
        self.lbl_checking_titulo.setText("ESPERANDO PAGO DEL CLIENTE")
        self.lbl_checking_titulo.setStyleSheet("font-size: 13px; font-weight: 900; color: #38bdf8;")
        self.lbl_checking_detalle.setText(f"Pida al cliente escanear el QR y transferir {CURRENCY} {monto_a_cobrar:.2f}:")
        self.lbl_checking_detalle.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 11px;")

        self.btn_verificar_checking.setText(f"⚡ Confirmar Pago de {CURRENCY} {monto_a_cobrar:.2f}")
        self.btn_verificar_checking.setEnabled(True)
        self.btn_verificar_checking.show()
        self.btn_deshacer_checking.hide()
        self.pbar_checking.hide()

        self.btn_confirmar.setEnabled(False)

    def _abrir_gestion_qr_cajero(self):
        if not self.usuario_id:
            return
        dlg = GestionQRDialog(self.usuario_id, parent=self)
        dlg.exec_()
        self._refrescar_panel_qr()

    def _mostrar_qr_popup(self):
        monto_mostrar = self.monto_qr if (self.metodo_pago == "mixto" and self.monto_qr > 0) else self.total
        qr_path_rel = self._obtener_qr_actual()
        ruta_real = resolver_ruta(qr_path_rel) if qr_path_rel else None
        if ruta_real and ruta_real.exists():
            dlg = VisualizadorImagenDialog(
                ruta_real,
                titulo=f"Código QR de Cobro – {CURRENCY} {monto_mostrar:.2f}",
                parent=self,
            )
            dlg.exec_()
        else:
            self._abrir_gestion_qr_cajero()

    def _adjuntar_comprobante_qr(self):
        arch, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Comprobante o Captura de Pago",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp);;Todos los archivos (*.*)",
        )
        if arch:
            self._comprobante_temp_path = arch
            nom = Path(arch).name
            self.lbl_adjunto_estado.setText(f"✓ Adjunto: {nom}")
            self.lbl_adjunto_estado.show()
            self.btn_adjuntar_qr.setText("🔄 Cambiar adjunto")

    def _adjuntar_comprobante_mixto(self):
        arch, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Comprobante o Captura de Pago QR",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp);;Todos los archivos (*.*)",
        )
        if arch:
            self._mixto_comprobante_temp_path = arch
            nom = Path(arch).name
            self.lbl_mixto_adjunto.setText(f"✓ Adjunto: {nom}")
            self.lbl_mixto_adjunto.show()
            self.btn_mixto_adjuntar.setText("🔄 Cambiar")

    def _on_qr_confirmado_toggle(self, checked: bool):
        if checked:
            self._qr_verificado = True
            self.card_confirmacion_qr.setStyleSheet("""
                QFrame#card_confirmacion_qr {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(34, 197, 94, 0.25), stop:1 rgba(21, 128, 61, 0.15));
                    border: 2px solid #22c55e;
                    border-radius: 10px;
                    padding: 8px;
                }
            """)
            self.lbl_checking_icon.setText("✅")
            self.lbl_checking_titulo.setText("¡PAGO CONFIRMADO MANUALMENTE!")
            self.lbl_checking_titulo.setStyleSheet("font-size: 13px; font-weight: 900; color: #22c55e;")
            self.btn_verificar_checking.hide()
            self.btn_deshacer_checking.show()
            self.btn_confirmar.setEnabled(True)
        else:
            self._reiniciar_checking()

    # ── Lógica de Efectivo Completo ───────────────────────────────────────────

    def _agregar_billete(self, valor: int):
        texto = self.input_monto.text().strip().replace(",", ".")
        try:
            actual = Decimal(texto) if texto else Decimal("0")
        except Exception:
            actual = Decimal("0")
        self.input_monto.setText(f"{actual + Decimal(str(valor)):.2f}")

    def _monto_exacto(self):
        self.input_monto.setText(f"{self.total:.2f}")

    def _actualizar_vuelto(self):
        if self.metodo_pago != "efectivo":
            return

        texto = self.input_monto.text().strip().replace(",", ".")
        try:
            recibido = Decimal(texto) if texto else Decimal("0")
        except Exception:
            recibido = Decimal("0")

        self.monto_recibido = recibido

        if recibido == 0:
            self.lbl_vuelto.setText("—")
            self.lbl_vuelto.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {PALETTE['text_muted']};")
            self.btn_confirmar.setEnabled(True)
        elif recibido < self.total:
            falta = self.total - recibido
            self.lbl_vuelto.setText(f"- {CURRENCY} {falta:.2f} (FALTA)")
            self.lbl_vuelto.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {PALETTE['danger']};")
            self.btn_confirmar.setEnabled(False)
        else:
            self.vuelto = recibido - self.total
            self.lbl_vuelto.setText(f"{CURRENCY} {self.vuelto:.2f}")
            self.lbl_vuelto.setStyleSheet(f"font-size: 28px; font-weight: 900; color: {PALETTE['success']};")
            self.btn_confirmar.setEnabled(True)

    def _on_enter_monto(self):
        if self.metodo_pago == "efectivo" and (not self.input_monto.text().strip() or self.monto_recibido == 0):
            self._monto_exacto()
        if self.btn_confirmar.isEnabled():
            self._confirmar()

    # ── Lógica de Pago Mixto (QR + Efectivo) ──────────────────────────────────

    def _mixto_efectivo_exacto(self):
        t_qr = self.input_mixto_qr.text().strip().replace(",", ".")
        try:
            m_qr = Decimal(t_qr) if t_qr else Decimal("0.00")
        except Exception:
            m_qr = Decimal("0.00")
        restante = max(Decimal("0.00"), self.total - m_qr)
        self.input_mixto_efectivo.setText(f"{restante:.2f}")

    def _actualizar_mixto(self):
        if self.metodo_pago != "mixto":
            return

        # 1. Leer monto QR
        t_qr = self.input_mixto_qr.text().strip().replace(",", ".")
        try:
            m_qr = Decimal(t_qr) if t_qr else Decimal("0.00")
        except Exception:
            m_qr = Decimal("0.00")
        if m_qr < 0:
            m_qr = Decimal("0.00")
        self.monto_qr = m_qr

        # 2. Calcular restante en efectivo
        if m_qr >= self.total:
            self.lbl_restante_efec.setText("⚠ QR cubre el total")
            self.lbl_restante_efec.setStyleSheet(f"color: {PALETTE['warning']}; font-size: 14px; font-weight: bold;")
            restante_efectivo = Decimal("0.00")
        else:
            restante_efectivo = self.total - m_qr
            self.lbl_restante_efec.setText(f"Resta en efectivo: {CURRENCY} {restante_efectivo:.2f}")
            self.lbl_restante_efec.setStyleSheet(f"color: {PALETTE['warning']}; font-size: 14px; font-weight: bold;")

        self.monto_efectivo = restante_efectivo

        # 3. Leer efectivo recibido
        t_ef = self.input_mixto_efectivo.text().strip().replace(",", ".")
        try:
            ef_rec = Decimal(t_ef) if t_ef else Decimal("0.00")
        except Exception:
            ef_rec = Decimal("0.00")
        self.efectivo_recibido = ef_rec

        # 4. Validar confirmación QR
        qr_ok = True
        if m_qr > 0:
            qr_ok = self.chk_mixto_qr_confirmado.isChecked()

        # 5. Validar montos y vuelto
        if m_qr == 0 and ef_rec == 0:
            self.lbl_mixto_vuelto.setText("—")
            self.lbl_mixto_vuelto.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {PALETTE['text_muted']}; border: none;")
            self.btn_confirmar.setEnabled(False)
        elif m_qr > self.total:
            self.lbl_mixto_vuelto.setText("⚠ QR supera total")
            self.lbl_mixto_vuelto.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {PALETTE['danger']}; border: none;")
            self.btn_confirmar.setEnabled(False)
        elif ef_rec < restante_efectivo:
            falta = restante_efectivo - ef_rec
            self.lbl_mixto_vuelto.setText(f"- {CURRENCY} {falta:.2f} (FALTA)")
            self.lbl_mixto_vuelto.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {PALETTE['danger']}; border: none;")
            self.btn_confirmar.setEnabled(False)
        elif not qr_ok:
            self.vuelto = ef_rec - restante_efectivo
            self.lbl_mixto_vuelto.setText("⚠ Confirme pago QR")
            self.lbl_mixto_vuelto.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {PALETTE['warning']}; border: none;")
            self.btn_confirmar.setEnabled(False)
        else:
            self.vuelto = ef_rec - restante_efectivo
            self.lbl_mixto_vuelto.setText(f"{CURRENCY} {self.vuelto:.2f}")
            self.lbl_mixto_vuelto.setStyleSheet(f"font-size: 28px; font-weight: 900; color: {PALETTE['success']}; border: none;")
            self.btn_confirmar.setEnabled(True)

    def _on_enter_mixto_efectivo(self):
        if not self.input_mixto_efectivo.text().strip() or self.efectivo_recibido == 0:
            self._mixto_efectivo_exacto()
        if self.btn_confirmar.isEnabled():
            self._confirmar()

    # ── Confirmar Venta ───────────────────────────────────────────────────────

    def _confirmar(self):
        self.lbl_error.hide()
        metodo = self.metodo_pago
        observacion = None
        qr_conf = False
        ref_pago = None
        comp_pago = None

        if metodo == "efectivo":
            if self.monto_recibido == 0:
                self.monto_recibido = self.total
                self.vuelto = Decimal("0.00")
            if self.vuelto > 0:
                observacion = f"Efectivo recibido: Bs {self.monto_recibido:.2f} | Vuelto: Bs {self.vuelto:.2f}"
        elif metodo == "QR":
            if not (self._qr_verificado or self.chk_confirmar_qr.isChecked()):
                self.lbl_error.setText("⚠ Debe confirmar que el cliente realizó el pago por QR antes de finalizar la venta.")
                self.lbl_error.show()
                return
            qr_conf = True
            ref_pago = self.input_ref_qr.text().strip() or self._codigo_referencia_generado
            if self._comprobante_temp_path and Path(self._comprobante_temp_path).exists():
                try:
                    comp_pago = guardar_comprobante_pago(self._comprobante_temp_path, prefijo="qr")
                except Exception:
                    comp_pago = None
            if ref_pago:
                observacion = f"Pago QR verificado. Ref: {ref_pago}"
            else:
                observacion = "Pago QR verificado con checking."
            self.monto_recibido = self.total
            self.vuelto = Decimal("0.00")
        elif metodo == "mixto":
            if self.monto_qr + self.monto_efectivo < self.total:
                self.lbl_error.setText("⚠ La suma de QR y Efectivo no cubre el total.")
                self.lbl_error.show()
                return
            if self.monto_qr > 0 and not self.chk_mixto_qr_confirmado.isChecked():
                self.lbl_error.setText("⚠ Debe confirmar la recepción del monto correspondiente a QR.")
                self.lbl_error.show()
                return
            qr_conf = (self.monto_qr > 0 and self.chk_mixto_qr_confirmado.isChecked())
            ref_pago = self.input_mixto_ref_qr.text().strip() or self._codigo_referencia_generado
            if self._mixto_comprobante_temp_path and Path(self._mixto_comprobante_temp_path).exists():
                try:
                    comp_pago = guardar_comprobante_pago(self._mixto_comprobante_temp_path, prefijo="mixto")
                except Exception:
                    comp_pago = None
            observacion = (
                f"Pago Mixto: QR Bs {self.monto_qr:.2f} + Efectivo Bs {self.monto_efectivo:.2f}"
            )
            if ref_pago:
                observacion += f" | Ref QR: {ref_pago}"
            if self.vuelto > 0:
                observacion += f" (Recibió efec. Bs {self.efectivo_recibido:.2f} | Vuelto: Bs {self.vuelto:.2f})"
            self.monto_recibido = self.monto_qr + self.efectivo_recibido
        else:
            self.monto_recibido = self.total
            self.vuelto = Decimal("0.00")

        items_ids = [(it["producto"].id, it["cantidad"]) for it in self.items]
        cliente_id = self.cliente_id
        usuario_id = self.usuario_id

        try:
            with get_session() as tx:
                from models.usuario import Usuario as UsuarioModel
                items_frescos = [
                    {"producto": tx.get(Producto, pid), "cantidad": cant}
                    for pid, cant in items_ids
                ]
                usuario_tx = tx.get(UsuarioModel, usuario_id)
                cliente_tx = tx.get(Cliente, cliente_id) if cliente_id else None

                venta = registrar_venta(
                    session=tx,
                    usuario=usuario_tx,
                    items=items_frescos,
                    metodo_pago=metodo,
                    cliente=cliente_tx,
                    observacion=observacion,
                    sesion_caja_id=self.sesion_caja_id,
                    qr_confirmado=qr_conf,
                    referencia_pago=ref_pago,
                    comprobante_pago=comp_pago,
                )

                # Generar Ticket PDF
                pdf_ruta = None
                try:
                    tx.flush()
                    for d in venta.detalles:
                        _ = d.producto
                    _ = venta.usuario
                    if venta.cliente_id:
                        _ = venta.cliente
                    pdf_ruta = generar_ticket_pdf(venta)
                except Exception:
                    pass

                cli_nombre = getattr(self.cliente, "razon_social", "Público General") if self.cliente else "Público General"
                self.pdf_path = pdf_ruta
                self.venta_registrada = {
                    "numero": venta.numero_transaccion,
                    "total": venta.total_bs,
                    "metodo": metodo,
                    "monto_recibido": self.monto_recibido,
                    "vuelto": self.vuelto,
                    "monto_qr": self.monto_qr if metodo == "mixto" else (self.total if metodo == "QR" else Decimal("0.00")),
                    "monto_efectivo": self.monto_efectivo if metodo == "mixto" else (self.total if metodo == "efectivo" else Decimal("0.00")),
                    "efectivo_recibido": self.efectivo_recibido if metodo == "mixto" else Decimal("0.00"),
                    "observacion": observacion,
                    "cliente": cli_nombre,
                    "cajero": self.usuario_username,
                    "qr_confirmado": qr_conf,
                    "referencia_pago": ref_pago,
                    "comprobante_pago": comp_pago,
                }

            self.accept()

        except StockInsuficienteError as e:
            self.lbl_error.setText(
                f"⚠ Stock insuficiente: {e.producto.descripcion}\n"
                f"Disponible: {e.disponible} – Requerido: {e.requerido}"
            )
            self.lbl_error.show()
        except Exception as e:
            self.lbl_error.setText(f"Error al registrar venta: {e}")
            self.lbl_error.show()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        elif event.key() == Qt.Key_Space and self.metodo_pago == "QR" and not self._qr_verificado:
            self._iniciar_verificacion_checking()
            return
        super().keyPressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  DIÁLOGO DE VENTA COMPLETADA (CAMBIO / VUELTO Y TICKET)
# ══════════════════════════════════════════════════════════════════════════════

class CobroExitosoDialog(QDialog):
    """
    Pantalla post-cobro que muestra claramente el cambio a entregar.
    Permanece visible hasta que el cajero entregue el vuelto y presione 'Siguiente Venta'.
    ¡No desaparece automáticamente!
    """

    def __init__(self, venta_info: dict, pdf_path: Path | None = None, parent=None):
        super().__init__(parent)
        self.venta_info = venta_info
        self.pdf_path = pdf_path
        self.setWindowTitle("✓ Venta Completada – Caja Mini Market")
        self.setMinimumSize(540, 620)
        self.resize(550, 640)
        self.setModal(True)
        self._build_ui()

    def showEvent(self, event):
        super().showEvent(event)
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.x() + (screen.width() - self.width()) // 2
            y = screen.y() + (screen.height() - self.height()) // 2
            self.move(max(10, x), max(10, y))
        except Exception:
            pass

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(14)

        # Encabezado con Icono
        hdr_lay = QVBoxLayout()
        hdr_lay.setAlignment(Qt.AlignCenter)
        hdr_lay.setSpacing(6)

        lbl_icon = QLabel("✅")
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet("font-size: 50px; border: none; background: transparent;")
        hdr_lay.addWidget(lbl_icon)

        lbl_tit = QLabel("¡COBRO REGISTRADO CON ÉXITO!")
        lbl_tit.setAlignment(Qt.AlignCenter)
        lbl_tit.setStyleSheet(f"font-size: 22px; font-weight: 900; color: {PALETTE['success']}; border: none; background: transparent;")
        hdr_lay.addWidget(lbl_tit)

        num_tx = self.venta_info.get("numero", 0)
        lbl_sub = QLabel(f"Comprobante N° #{num_tx:06d}")
        lbl_sub.setAlignment(Qt.AlignCenter)
        lbl_sub.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {PALETTE['text_secondary']}; border: none; background: transparent;")
        hdr_lay.addWidget(lbl_sub)

        lay.addLayout(hdr_lay)

        # Tarjeta de detalles de cobro
        card = QFrame()
        card.setObjectName("card_exito")
        card.setStyleSheet(f"""
            QFrame#card_exito {{
                background: {PALETTE['bg_card']};
                border: none;
                border-radius: 14px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        c_lay = QVBoxLayout(card)
        c_lay.setContentsMargins(18, 16, 18, 16)
        c_lay.setSpacing(12)

        # Fila Total
        f_total = QHBoxLayout()
        lbl_t_txt = QLabel("Total de la compra:")
        lbl_t_txt.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 14px; font-weight: 600;")
        f_total.addWidget(lbl_t_txt)
        f_total.addStretch()
        lbl_t_val = QLabel(f"{CURRENCY} {self.venta_info['total']:.2f}")
        lbl_t_val.setStyleSheet(f"font-size: 26px; font-weight: 900; color: {PALETTE['white']};")
        f_total.addWidget(lbl_t_val)
        c_lay.addLayout(f_total)

        # Fila Método y Desglose
        metodo = self.venta_info["metodo"]
        f_metodo = QHBoxLayout()
        lbl_m_txt = QLabel("Método de pago:")
        lbl_m_txt.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 14px; font-weight: 600;")
        f_metodo.addWidget(lbl_m_txt)
        f_metodo.addStretch()

        if metodo == "mixto":
            lbl_m_val = QLabel("🔄 Pago Mixto (QR + Efectivo)")
            lbl_m_val.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {PALETTE['accent']};")
            f_metodo.addWidget(lbl_m_val)
            c_lay.addLayout(f_metodo)

            # Tarjeta con desglose de Pago Mixto
            desglose_box = QFrame()
            desglose_box.setObjectName("desglose_box")
            desglose_box.setStyleSheet("""
                QFrame#desglose_box {
                    background: rgba(15, 23, 42, 0.7);
                    border: none;
                    border-radius: 10px;
                }
                QLabel {
                    border: none;
                    background: transparent;
                    font-size: 14px;
                }
            """)
            d_lay = QVBoxLayout(desglose_box)
            d_lay.setContentsMargins(12, 10, 12, 10)
            d_lay.setSpacing(6)

            d_qr = QHBoxLayout()
            d_qr.addWidget(QLabel("📱 Pagado por QR:"))
            d_qr.addStretch()
            lbl_qr_val = QLabel(f"{CURRENCY} {self.venta_info.get('monto_qr', Decimal('0')):.2f}")
            lbl_qr_val.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {PALETTE['accent']};")
            d_qr.addWidget(lbl_qr_val)
            d_lay.addLayout(d_qr)

            d_ef = QHBoxLayout()
            d_ef.addWidget(QLabel("💵 Porción en Efectivo:"))
            d_ef.addStretch()
            lbl_ef_val = QLabel(f"{CURRENCY} {self.venta_info.get('monto_efectivo', Decimal('0')):.2f}")
            lbl_ef_val.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {PALETTE['white']};")
            d_ef.addWidget(lbl_ef_val)
            d_lay.addLayout(d_ef)

            ef_rec = self.venta_info.get('efectivo_recibido', Decimal('0'))
            if ef_rec > self.venta_info.get('monto_efectivo', Decimal('0')):
                d_rec = QHBoxLayout()
                d_rec.addWidget(QLabel("💵 Billete entregado:"))
                d_rec.addStretch()
                lbl_rec_val = QLabel(f"{CURRENCY} {ef_rec:.2f}")
                lbl_rec_val.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 14px;")
                d_rec.addWidget(lbl_rec_val)
                d_lay.addLayout(d_rec)

            c_lay.addWidget(desglose_box)
        else:
            recibido = self.venta_info.get("monto_recibido", Decimal("0"))
            if metodo == "QR":
                det_pago = "📱 QR Simple (✓ Pago Verificado)"
                color_m = PALETTE['success']
            elif metodo == "efectivo":
                det_pago = f"💵 Efectivo (Recibido: {CURRENCY} {recibido:.2f})"
                color_m = PALETTE['text_primary']
            else:
                det_pago = metodo.capitalize()
                color_m = PALETTE['text_primary']

            lbl_m_val = QLabel(det_pago)
            lbl_m_val.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color_m};")
            f_metodo.addWidget(lbl_m_val)
            c_lay.addLayout(f_metodo)

        # Información de Verificación QR y Comprobante
        ref = self.venta_info.get("referencia_pago")
        comp = self.venta_info.get("comprobante_pago")
        qr_conf = self.venta_info.get("qr_confirmado", False)
        if metodo == "QR" or (metodo == "mixto" and qr_conf):
            qr_conf_box = QFrame()
            qr_conf_box.setObjectName("qr_conf_box")
            qr_conf_box.setStyleSheet(f"""
                QFrame#qr_conf_box {{
                    background: rgba(34, 197, 94, 0.12);
                    border: 1px solid rgba(34, 197, 94, 0.35);
                    border-radius: 8px;
                }}
                QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)
            qcb_lay = QVBoxLayout(qr_conf_box)
            qcb_lay.setContentsMargins(12, 8, 12, 8)
            qcb_lay.setSpacing(4)
            lbl_qc = QLabel("✓ Pago QR verificado exitosamente por el cajero")
            lbl_qc.setStyleSheet(f"color: {PALETTE['success']}; font-size: 13px; font-weight: bold;")
            lbl_qc.setMinimumHeight(20)
            qcb_lay.addWidget(lbl_qc)
            if ref:
                lbl_r = QLabel(f"N° Referencia: <b>{ref}</b>")
                lbl_r.setStyleSheet(f"color: {PALETTE['text_primary']}; font-size: 12px;")
                qcb_lay.addWidget(lbl_r)
            if comp:
                lbl_c = QLabel(f"📎 Comprobante guardado: {Path(comp).name}")
                lbl_c.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 11px;")
                qcb_lay.addWidget(lbl_c)
            c_lay.addWidget(qr_conf_box)

        # Bloque de Vuelto / Cambio (Destacado y Elegante)
        vuelto = self.venta_info.get("vuelto", Decimal("0"))
        vuelto_box = QFrame()
        vuelto_box.setObjectName("vuelto_box")
        if vuelto > 0:
            vuelto_box.setStyleSheet("""
                QFrame#vuelto_box {
                    background: #064e3b;
                    border: none;
                    border-radius: 14px;
                }
                QLabel {
                    border: none;
                    background: transparent;
                }
            """)
            vb_lay = QVBoxLayout(vuelto_box)
            vb_lay.setContentsMargins(18, 14, 18, 14)
            vb_lay.setAlignment(Qt.AlignCenter)
            vb_lay.setSpacing(6)

            lbl_vb_tit = QLabel("💵 VUELTO A ENTREGAR AL CLIENTE (EN EFECTIVO):")
            lbl_vb_tit.setAlignment(Qt.AlignCenter)
            lbl_vb_tit.setStyleSheet("color: #a7f3d0; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
            vb_lay.addWidget(lbl_vb_tit)

            lbl_vb_val = QLabel(f"{CURRENCY} {vuelto:.2f}")
            lbl_vb_val.setAlignment(Qt.AlignCenter)
            lbl_vb_val.setStyleSheet("font-size: 38px; font-weight: 900; color: #4ade80;")
            vb_lay.addWidget(lbl_vb_val)

            lbl_vb_sub = QLabel("Entregue el dinero de cambio al cliente antes de continuar.")
            lbl_vb_sub.setAlignment(Qt.AlignCenter)
            lbl_vb_sub.setWordWrap(True)
            lbl_vb_sub.setStyleSheet("color: #d1fae5; font-size: 13px; font-weight: 500;")
            vb_lay.addWidget(lbl_vb_sub)
        else:
            vuelto_box.setStyleSheet(f"""
                QFrame#vuelto_box {{
                    background: {PALETTE['bg_surface']};
                    border: none;
                    border-radius: 10px;
                }}
                QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)
            vb_lay = QVBoxLayout(vuelto_box)
            vb_lay.setContentsMargins(16, 12, 16, 12)
            vb_lay.setAlignment(Qt.AlignCenter)
            lbl_no_vuelto = QLabel("✓ Monto exacto cubierto – Sin cambio pendiente")
            lbl_no_vuelto.setAlignment(Qt.AlignCenter)
            lbl_no_vuelto.setStyleSheet(f"color: {PALETTE['success']}; font-size: 14px; font-weight: bold;")
            vb_lay.addWidget(lbl_no_vuelto)

        c_lay.addWidget(vuelto_box)
        lay.addWidget(card)

        lay.addStretch()

        # Botones de Acción
        actions_lay = QVBoxLayout()
        actions_lay.setSpacing(12)

        if self.pdf_path:
            btn_ticket = QPushButton("🖨️  Ver / Imprimir Ticket PDF")
            btn_ticket.setFixedHeight(46)
            btn_ticket.setStyleSheet(f"""
                QPushButton {{
                    background: {PALETTE['bg_hover']};
                    color: {PALETTE['accent']};
                    border: none;
                    border-radius: 10px;
                    font-size: 14px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: {PALETTE['accent']};
                    color: white;
                }}
            """)
            btn_ticket.clicked.connect(self._abrir_ticket)
            actions_lay.addWidget(btn_ticket)

        self.btn_siguiente = QPushButton("➡️  Siguiente Venta  [Enter]")
        self.btn_siguiente.setFixedHeight(50)
        self.btn_siguiente.setDefault(True)
        self.btn_siguiente.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['success']};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #16a34a; }}
            QPushButton:pressed {{ background: #15803d; }}
        """)
        self.btn_siguiente.clicked.connect(self.accept)
        actions_lay.addWidget(self.btn_siguiente)

        lay.addLayout(actions_lay)

        QTimer.singleShot(100, self.btn_siguiente.setFocus)

    def _abrir_ticket(self):
        if self.pdf_path and Path(self.pdf_path).exists():
            try:
                os.startfile(str(self.pdf_path))
            except Exception as e:
                QMessageBox.information(self, "Ticket", f"Archivo generado en:\n{self.pdf_path}")
        else:
            QMessageBox.warning(self, "Ticket", "El archivo de ticket no se encuentra disponible.")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space, Qt.Key_Escape):
            self.accept()
            return
        super().keyPressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  WIDGET PRINCIPAL DEL PUNTO DE VENTA (POS)
# ══════════════════════════════════════════════════════════════════════════════

class POSWidget(QWidget):
    """Panel interactivo del Punto de Venta."""

    def __init__(self, usuario: Usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.session = SessionLocal()
        self._sesion_caja_activa: SesionCaja | None = None
        self._caja_activa_id: int | None = None
        self._caja_activa_turno: str = ""
        self._caja_activa_monto_inicial: Decimal = Decimal("0.00")
        self._items: list[dict] = []
        self._cliente = None
        self._total_actual = Decimal("0.00")
        self._ultima_venta = None
        self._ultimo_ticket_pdf = None

        self._build_ui()
        self._verificar_caja_activa()
        self._setup_shortcuts()
        self._setup_autocomplete()
        self._restaurar_foco_barcode()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Columna Central: Todo el Lienzo Central POS ───────────────────────
        bg_pos = PALETTE.get("pos_center", "#F3FF78")
        fg_pos = PALETTE.get("pos_text", "#000000")

        center_canvas = QFrame()
        center_canvas.setObjectName("pos_center_canvas")
        center_canvas.setStyleSheet(f"""
            QFrame#pos_center_canvas {{
                background-color: {bg_pos};
                border-right: 2px solid #0f1117;
            }}
        """)
        left = QVBoxLayout(center_canvas)
        left.setContentsMargins(18, 16, 18, 16)
        left.setSpacing(12)

        # ── Fila 1: Título Centrado Grande y Legible desde lejos ───────────────
        lbl_tit = QLabel("PUNTO DE VENTA")
        lbl_tit.setAlignment(Qt.AlignCenter)
        lbl_tit.setStyleSheet(f"font-size: 26px; font-weight: 900; color: {fg_pos}; letter-spacing: 3px; background: transparent;")
        left.addWidget(lbl_tit)

        es_admin = self.usuario.es_admin()

        # ── Fila 2: Atajos y Controles de Caja Alineados ───────────────────────
        sub_header = QHBoxLayout()
        sub_header.setSpacing(10)
        sub_header.setAlignment(Qt.AlignVCenter)

        # Atajos rápidos a la izquierda
        shortcuts_box = QHBoxLayout()
        shortcuts_box.setSpacing(6)
        shortcuts_box.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        atajos = [
            ("Enter", "Escanear"),
            ("F11", "Buscar"),
            ("F12", "Cobrar"),
        ]
        if not es_admin:
            atajos.append(("F9", "Caja"))
        atajos.extend([
            ("Del", "Quitar"),
            ("Esc", "Cancelar"),
        ])
        for key, desc in atajos:
            chip = QLabel(f"<b style='color: #000000;'>{key}</b> {desc}")
            chip.setFixedHeight(30)
            chip.setAlignment(Qt.AlignCenter)
            chip.setStyleSheet("""
                QLabel {
                    background: #ffffff;
                    color: #0f172a;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 3px 8px;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
            shortcuts_box.addWidget(chip)

        sub_header.addLayout(shortcuts_box)
        sub_header.addStretch()

        # Acciones de Caja y Cajero a la derecha (Alineados a 36px exactos)
        right_header = QHBoxLayout()
        right_header.setSpacing(8)
        right_header.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Badge indicador de Sesión de Caja
        self.badge_caja = QLabel("🔴 Caja Cerrada")
        self.badge_caja.setFixedHeight(36)
        self.badge_caja.setAlignment(Qt.AlignCenter)
        self.badge_caja.setStyleSheet("""
            background: #ffffff;
            color: #b91c1c;
            border: 2px solid #b91c1c;
            border-radius: 8px;
            padding: 4px 12px;
            font-size: 13px;
            font-weight: bold;
        """)
        right_header.addWidget(self.badge_caja)

        # Botón de Apertura / Cierre rápido de Caja
        self.btn_caja_accion = QPushButton("🔓 Abrir Caja")
        self.btn_caja_accion.setFixedHeight(36)
        self.btn_caja_accion.setCursor(Qt.PointingHandCursor)
        self.btn_caja_accion.setStyleSheet("""
            QPushButton {
                background: #0f172a;
                color: #ffffff;
                border: 2px solid #000000;
                border-radius: 8px;
                padding: 4px 14px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2563eb;
                border-color: #2563eb;
            }
        """)
        self.btn_caja_accion.clicked.connect(self._gestionar_caja)
        right_header.addWidget(self.btn_caja_accion)

        if es_admin:
            self.badge_caja.hide()
            self.btn_caja_accion.hide()
            lbl_usuario_txt = f"🛡️ <b>{self.usuario.username}</b>"
        else:
            lbl_usuario_txt = f"👤 Cajero: <b>{self.usuario.username}</b>"

        lbl_cajero = QLabel(lbl_usuario_txt)
        lbl_cajero.setFixedHeight(36)
        lbl_cajero.setAlignment(Qt.AlignVCenter)
        lbl_cajero.setStyleSheet(f"color: {fg_pos}; font-size: 13px; font-weight: bold; background: transparent;")
        right_header.addWidget(lbl_cajero)

        # Botón de Configuración de Código QR para Cobrar
        self.btn_mi_qr = QPushButton("📱 Mi QR")
        self.btn_mi_qr.setFixedHeight(36)
        self.btn_mi_qr.setCursor(Qt.PointingHandCursor)
        self.btn_mi_qr.clicked.connect(self._abrir_gestion_qr)
        right_header.addWidget(self.btn_mi_qr)
        self._actualizar_badge_qr()

        sub_header.addLayout(right_header)
        left.addLayout(sub_header)

        # Barra de Entrada de Código de Barras (Card blanca flotante sobre fondo claro)
        scan_card = QFrame()
        scan_card.setObjectName("pos_scan_card")
        scan_card.setStyleSheet("""
            QFrame#pos_scan_card {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
            }
        """)
        shadow_scan = QGraphicsDropShadowEffect(scan_card)
        shadow_scan.setBlurRadius(14)
        shadow_scan.setColor(QColor(0, 0, 0, 25))
        shadow_scan.setOffset(0, 3)
        scan_card.setGraphicsEffect(shadow_scan)

        scan_lay = QHBoxLayout(scan_card)
        scan_lay.setContentsMargins(10, 6, 10, 6)
        scan_lay.setSpacing(10)

        lbl_scan_icon = QLabel("📷")
        lbl_scan_icon.setStyleSheet("font-size: 22px; color: #000000; background: transparent;")
        scan_lay.addWidget(lbl_scan_icon)

        self.input_barcode = QLineEdit()
        self.input_barcode.setObjectName("barcode_input")
        self.input_barcode.setPlaceholderText("Escriba o escanee código de barras (o formato 3*codigo) y presione Enter...")
        self.input_barcode.setStyleSheet("""
            QLineEdit#barcode_input {
                font-size: 14px;
                font-weight: 600;
                color: #0f172a;
                background: #f8fafc;
                border: 1.5px solid #cbd5e1;
                border-radius: 8px;
                padding: 7px 12px;
            }
            QLineEdit#barcode_input:focus {
                border: 2px solid #2563eb;
                background: #ffffff;
            }
        """)
        self.input_barcode.returnPressed.connect(self._agregar_por_barcode)
        scan_lay.addWidget(self.input_barcode, 1)

        btn_buscar = QPushButton("🔍  F11 Buscar")
        btn_buscar.setObjectName("btn_pos_buscar")
        btn_buscar.setFixedHeight(38)
        btn_buscar.setCursor(Qt.PointingHandCursor)
        btn_buscar.setStyleSheet("""
            QPushButton#btn_pos_buscar {
                background-color: #0f172a;
                color: #ffffff;
                border: 1px solid #0f172a;
                border-radius: 8px;
                padding: 0px 18px;
                min-height: 38px;
                max-height: 38px;
                font-size: 14px;
                font-weight: 800;
                text-align: center;
            }
            QPushButton#btn_pos_buscar:hover {
                background-color: #2563eb;
                border-color: #2563eb;
                color: #ffffff;
            }
            QPushButton#btn_pos_buscar:pressed {
                background-color: #1d4ed8;
            }
        """)
        btn_buscar.clicked.connect(self._abrir_buscar)
        scan_lay.addWidget(btn_buscar)

        left.addWidget(scan_card)

        # ── Card Flotante para la Tabla de Ventas (Efecto Tarjeta Suave) ──────
        table_card = QFrame()
        table_card.setObjectName("pos_table_card")
        table_card.setStyleSheet("""
            QFrame#pos_table_card {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
            }
        """)
        shadow_table = QGraphicsDropShadowEffect(table_card)
        shadow_table.setBlurRadius(18)
        shadow_table.setColor(QColor(0, 0, 0, 25))
        shadow_table.setOffset(0, 4)
        table_card.setGraphicsEffect(shadow_table)

        table_card_lay = QVBoxLayout(table_card)
        table_card_lay.setContentsMargins(1, 1, 1, 1)
        table_card_lay.setSpacing(0)

        # Tabla de Carrito de Compras en el lienzo central
        self.tabla = QTableWidget(0, 8)
        headers = ["#", "Código", "Descripción", "UM", "Cantidad", f"P. Unit. ({CURRENCY})", f"Subtotal ({CURRENCY})", "Acción"]
        self.tabla.setHorizontalHeaderLabels(headers)
        self.tabla.horizontalHeader().setSectionResizeMode(COL_DESCRIPCION, QHeaderView.Stretch)
        self.tabla.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.tabla.setColumnWidth(COL_NUM, 46)
        self.tabla.setColumnWidth(COL_CODIGO, 135)
        self.tabla.setColumnWidth(COL_UM, 60)
        self.tabla.setColumnWidth(COL_CANTIDAD, 145)
        self.tabla.setColumnWidth(COL_PRECIO, 120)
        self.tabla.setColumnWidth(COL_SUBTOTAL, 130)
        self.tabla.setColumnWidth(COL_ACCIONES, 65)

        hdr_bg = PALETTE.get("pos_table_header_bg", "#111827")
        hdr_text = PALETTE.get("pos_table_header_text", "#ffffff")
        table_bg = PALETTE.get("pos_table_bg", "#ffffff")
        table_alt = PALETTE.get("pos_table_alt", "#f8fafc")
        table_text = PALETTE.get("pos_table_text", "#000000")

        for col_idx in range(8):
            hdr_item = self.tabla.horizontalHeaderItem(col_idx)
            if hdr_item:
                hdr_item.setTextAlignment(Qt.AlignCenter)
                hdr_item.setForeground(QColor(hdr_text))
                f = hdr_item.font()
                f.setPointSize(13)
                f.setBold(True)
                hdr_item.setFont(f)

        self.tabla.verticalHeader().setDefaultSectionSize(48)
        self.tabla.setStyleSheet(f"""
            QTableWidget {{
                background-color: {table_bg};
                gridline-color: #f1f5f9;
                border: none;
                border-radius: 11px;
                alternate-background-color: {table_alt};
                selection-background-color: #e2e8f0;
                selection-color: {table_text};
                color: {table_text};
                font-size: 14px;
            }}
            QTableWidget::item {{
                color: {table_text};
                padding: 4px 6px;
                border: none;
            }}
            QTableWidget::item:selected {{
                background-color: #e2e8f0;
                color: {table_text};
            }}
            QHeaderView::section {{
                background-color: {hdr_bg};
                color: {hdr_text};
                border: none;
                border-bottom: 2px solid #cbd5e1;
                border-right: 1px solid #374151;
                padding: 9px 4px;
                font-weight: 900;
                font-size: 13px;
                text-align: center;
            }}
            QHeaderView::section:first {{
                border-top-left-radius: 11px;
            }}
            QHeaderView::section:last {{
                border-top-right-radius: 11px;
                border-right: none;
            }}
        """)

        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setShowGrid(True)
        self.tabla.cellChanged.connect(self._on_cell_changed)
        table_card_lay.addWidget(self.tabla)

        # ── Marca de agua: logo PeKeMarket centrado sobre la tabla ────────────
        self._wm_label = QLabel(table_card)
        self._wm_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._wm_label.setAlignment(Qt.AlignCenter)
        self._wm_label.setStyleSheet("background: transparent; border: none;")
        self._wm_label.raise_()

        _logo_path = str(Path(__file__).parent.parent / "assets" / "logo.png")
        _pix_orig = QPixmap(_logo_path)
        if _pix_orig.isNull():
            _logo_path = str(Path(__file__).parent.parent / "assets" / "logo.jpg")
            _pix_orig = QPixmap(_logo_path)

        self._wm_orig_pix = _pix_orig if not _pix_orig.isNull() else None
        self._wm_pix_size = None

        if self._wm_orig_pix is None:
            self._wm_label.setText(APP_NAME)

        # Conectar resize de table_card y viewport para recentrar la marca de agua
        table_card.installEventFilter(self)
        self.tabla.viewport().installEventFilter(self)
        self._wm_card = table_card

        left.addWidget(table_card, 1)

        root.addWidget(center_canvas, 1)

        # ── Columna Derecha: Panel de Control de Caja ─────────────────────────
        right = QFrame()
        right.setFixedWidth(310)
        right.setStyleSheet("""
            QFrame {
                background: #111827;
                border: none;
            }
        """)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(12, 14, 12, 14)
        right_lay.setSpacing(10)

        # ── Bloque 1: TOTAL A COBRAR ──────────────────────────────────────────
        total_card = QFrame()
        total_card.setStyleSheet("""
            QFrame {
                background-color: #1f293d;
                border: none;
                border-radius: 12px;
            }
        """)
        tot_lay = QVBoxLayout(total_card)
        tot_lay.setContentsMargins(16, 16, 16, 16)
        tot_lay.setSpacing(4)

        lbl_tot_title = QLabel("TOTAL A PAGAR")
        lbl_tot_title.setAlignment(Qt.AlignCenter)
        lbl_tot_title.setStyleSheet("color: #94a3b8; font-size: 14px; font-weight: bold; letter-spacing: 1.5px; background: transparent; border: none;")
        tot_lay.addWidget(lbl_tot_title)

        self.lbl_total = QLabel(f"{CURRENCY} 0.00")
        self.lbl_total.setAlignment(Qt.AlignCenter)
        self.lbl_total.setStyleSheet("""
            font-size: 42px;
            font-weight: 900;
            color: #ffffff;
            letter-spacing: -1px;
            background: transparent;
            border: none;
        """)
        tot_lay.addWidget(self.lbl_total)

        self.lbl_items_count = QLabel("Carrito vacío")
        self.lbl_items_count.setAlignment(Qt.AlignCenter)
        self.lbl_items_count.setStyleSheet("color: #e2e8f0; font-size: 14px; font-weight: 600; background: transparent; border: none;")
        tot_lay.addWidget(self.lbl_items_count)

        right_lay.addWidget(total_card)

        # ── Bloque 2: CLIENTE ─────────────────────────────────────────────────
        cli_card = QFrame()
        cli_card.setStyleSheet("""
            QFrame {
                background-color: #1f293d;
                border: none;
                border-radius: 12px;
            }
        """)
        cli_lay = QVBoxLayout(cli_card)
        cli_lay.setContentsMargins(14, 12, 14, 12)
        cli_lay.setSpacing(8)

        lbl_cli_hdr = QLabel("👤  CLIENTE (OPCIONAL)")
        lbl_cli_hdr.setStyleSheet("color: #e2e8f0; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        cli_lay.addWidget(lbl_cli_hdr)

        cli_row = QHBoxLayout()
        cli_row.setSpacing(8)
        self.input_nit = QLineEdit()
        self.input_nit.setPlaceholderText("NIT o Razón Social...")
        self.input_nit.setFixedHeight(38)
        self.input_nit.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a;
                color: #ffffff;
                font-size: 14px;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px 12px;
            }
            QLineEdit:focus {
                border: 1.5px solid #3b82f6;
                background-color: #131d31;
            }
        """)
        self.input_nit.returnPressed.connect(self._buscar_cliente)
        cli_row.addWidget(self.input_nit, 1)

        btn_bc = QPushButton()
        btn_bc.setFixedSize(38, 38)
        btn_bc.setCursor(Qt.PointingHandCursor)
        btn_bc.setToolTip("Buscar cliente por NIT o Razón Social (Enter)")
        _icon_search = Path(__file__).resolve().parent.parent / "assets" / "search_icon_white.png"
        if _icon_search.exists():
            btn_bc.setIcon(QIcon(str(_icon_search)))
            btn_bc.setIconSize(QSize(18, 18))
        else:
            btn_bc.setText("🔍")
        btn_bc.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
                color: #ffffff;
                font-size: 15px;
                font-weight: bold;
                border: 1px solid #60a5fa;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #60a5fa, stop:1 #3b82f6);
                border: 1px solid #93c5fd;
            }
            QPushButton:pressed {
                background: #1d4ed8;
            }
        """)
        btn_bc.clicked.connect(self._buscar_cliente)
        cli_row.addWidget(btn_bc)
        cli_lay.addLayout(cli_row)

        self.lbl_cliente = QLabel("Público General  (Sin NIT)")
        self.lbl_cliente.setStyleSheet("color: #94a3b8; font-size: 14px; background: transparent; border: none;")
        cli_lay.addWidget(self.lbl_cliente)

        right_lay.addWidget(cli_card)

        # ── Bloque 3: ÚLTIMA VENTA REGISTRADA (Persistente) ────────────────────
        self.ultima_venta_card = QFrame()
        self.ultima_venta_card.setStyleSheet("""
            QFrame {
                background-color: #1f293d;
                border: none;
                border-radius: 12px;
            }
        """)
        uv_lay = QVBoxLayout(self.ultima_venta_card)
        uv_lay.setContentsMargins(14, 12, 14, 12)
        uv_lay.setSpacing(8)

        lbl_uv_hdr = QLabel("🧾  ÚLTIMA VENTA REALIZADA")
        lbl_uv_hdr.setStyleSheet("color: #e2e8f0; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        uv_lay.addWidget(lbl_uv_hdr)

        self.lbl_uv_info = QLabel("Ninguna venta registrada aún en esta sesión.")
        self.lbl_uv_info.setWordWrap(True)
        self.lbl_uv_info.setStyleSheet("color: #94a3b8; font-size: 14px; background: transparent; border: none;")
        uv_lay.addWidget(self.lbl_uv_info)

        self.btn_reimprimir_ticket = QPushButton("🖨️  Reimprimir Ticket")
        self.btn_reimprimir_ticket.setFixedHeight(34)
        self.btn_reimprimir_ticket.setCursor(Qt.PointingHandCursor)
        self.btn_reimprimir_ticket.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.btn_reimprimir_ticket.hide()
        self.btn_reimprimir_ticket.clicked.connect(self._reimprimir_ultimo_ticket)
        uv_lay.addWidget(self.btn_reimprimir_ticket)

        right_lay.addWidget(self.ultima_venta_card)

        # ── Bloque 4: Mini Resumen de ítems recientes ─────────────────────────
        resumen_box = QFrame()
        resumen_box.setStyleSheet("""
            QFrame {
                background-color: #1f293d;
                border: none;
                border-radius: 12px;
            }
        """)
        res_lay = QVBoxLayout(resumen_box)
        res_lay.setContentsMargins(14, 12, 14, 12)
        res_lay.setSpacing(6)

        lbl_res_h = QLabel("🛒  Artículos en curso")
        lbl_res_h.setStyleSheet("color: #e2e8f0; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        res_lay.addWidget(lbl_res_h)

        self.lista_resumen = QListWidget()
        self.lista_resumen.setFixedHeight(85)
        self.lista_resumen.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                font-size: 14px;
                color: #cbd5e1;
            }
            QListWidget::item {
                padding: 3px 0;
                border: none;
            }
        """)
        self.lista_resumen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        res_lay.addWidget(self.lista_resumen)

        right_lay.addWidget(resumen_box)
        right_lay.addStretch()

        # ── Bloque 5: Botones de Acción (COBRAR / CANCELAR) ───────────────────
        acciones_card = QFrame()
        acciones_card.setStyleSheet("""
            QFrame {
                background-color: #1f293d;
                border: none;
                border-radius: 12px;
            }
        """)
        acc_lay = QVBoxLayout(acciones_card)
        acc_lay.setContentsMargins(14, 14, 14, 14)
        acc_lay.setSpacing(10)

        # Mensaje de estado
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #22c55e; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        acc_lay.addWidget(self.lbl_status)

        # Botón gigante F12 COBRAR
        self.btn_cobrar = QPushButton("COBRAR")
        self.btn_cobrar.setEnabled(False)
        self.btn_cobrar.setFixedHeight(54)
        self.btn_cobrar.setCursor(Qt.PointingHandCursor)
        self.btn_cobrar.setStyleSheet("""
            QPushButton {
                background-color: #16a34a;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: 900;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background-color: #15803d;
            }
            QPushButton:pressed {
                background-color: #166534;
            }
            QPushButton:disabled {
                background-color: #334155;
                color: #94a3b8;
                font-size: 15px;
            }
        """)
        self.btn_cobrar.clicked.connect(self._abrir_cobro)
        acc_lay.addWidget(self.btn_cobrar)

        # Botón Cancelar Venta
        btn_cancelar = QPushButton("X  Cancelar Venta  (Esc)")
        btn_cancelar.setFixedHeight(40)
        btn_cancelar.setCursor(Qt.PointingHandCursor)
        btn_cancelar.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
            QPushButton:pressed {
                background-color: #b91c1c;
            }
        """)
        btn_cancelar.clicked.connect(self._limpiar_venta)
        acc_lay.addWidget(btn_cancelar)

        right_lay.addWidget(acciones_card)

        root.addWidget(right, 0)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("F12"), self).activated.connect(self._abrir_cobro)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._limpiar_venta)
        QShortcut(QKeySequence("F11"), self).activated.connect(self._abrir_buscar)
        if not self.usuario.es_admin():
            QShortcut(QKeySequence("F9"), self).activated.connect(self._gestionar_caja)
        QShortcut(QKeySequence("Delete"), self).activated.connect(self._eliminar_fila_seleccionada)

    def _restaurar_foco_barcode(self):
        QTimer.singleShot(100, self.input_barcode.setFocus)

    # ── Autocompletado en Tiempo Real ─────────────────────────────────────────

    def _setup_autocomplete(self):
        """Configura el autocompletado en tiempo real con ventana emergente interactiva."""
        self._completer_model = QStandardItemModel(self)
        self.completer = QCompleter(self._completer_model, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setMaxVisibleItems(10)

        # Estilo visual moderno, amplio y legible del menú flotante de sugerencias
        popup = self.completer.popup()
        popup.setFont(QFont("Segoe UI", 13))
        popup.setMinimumWidth(720)
        
        popup.setStyleSheet("""
            QListView {
                background-color: #ffffff;
                color: #000000;
                font-size: 13px;
                font-weight: 600;
                border: 2px solid #2563eb;
                border-radius: 8px;
                padding: 2px;
                outline: none;
            }
            QListView::item {
                padding: 6px 12px;
                border-bottom: 1px solid #e2e8f0;
                border-radius: 4px;
            }
            QListView::item:hover {
                background-color: #dbeafe;
                color: #1d4ed8;
            }
            QListView::item:selected {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
            }
            QScrollBar:vertical {
                background: #f1f5f9;
                width: 10px;
                border-radius: 5px;
                margin: 2px 2px 2px 0px;
            }
            QScrollBar::handle:vertical {
                background: #94a3b8;
                border-radius: 5px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: #64748b;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.completer.activated[QModelIndex].connect(self._on_completer_item_activated)
        self.input_barcode.setCompleter(self.completer)
        self.input_barcode.textEdited.connect(self._on_barcode_text_edited)
        self.input_barcode.installEventFilter(self)
        self._actualizar_autocompletado()

    def _actualizar_autocompletado(self):
        """Recarga la lista de productos activos para autocompletado en tiempo real."""
        self._completer_model.clear()
        try:
            productos = self.session.query(Producto).filter_by(activo=True).order_by(Producto.descripcion).all()
            for p in productos:
                stock_txt = f"{p.stock_actual:.0f} {p.unidad_medida}"
                texto = f"{p.descripcion}   —   {CURRENCY} {p.precio_venta_bs:.2f}   (Stock: {stock_txt})   [{p.codigo_barras}]"
                item = QStandardItem(texto)
                item.setData(p, Qt.UserRole)
                item.setSizeHint(QSize(0, 42))  # Altura exacta de fila para que NUNCA se recorte
                self._completer_model.appendRow(item)
        except Exception:
            pass

    def _mostrar_todos_los_productos(self):
        """Despliega la lista completa con todos los productos registrados."""
        if self._completer_model.rowCount() == 0:
            self._actualizar_autocompletado()
        self.completer.setCompletionPrefix("")
        self.completer.complete()

    def _on_barcode_text_edited(self, text: str):
        """Filtra en tiempo real según lo que escribe el cajero (soporta 3*coca)."""
        cleaned = text.strip()
        if not cleaned:
            # Si el campo se limpia, muestra todos los productos disponibles
            self._mostrar_todos_los_productos()
            return

        if "*" in text:
            partes = text.split("*", 1)
            query = partes[1].strip() if len(partes) > 1 else ""
            self.completer.setCompletionPrefix(query)
        else:
            self.completer.setCompletionPrefix(cleaned)

        self.completer.complete()

    def eventFilter(self, obj, event):
        """Maneja eventos de widgets filtrados:
        - input_barcode: click o flecha abajo para abrir catálogo completo
        - table_card: reposiciona la marca de agua en cualquier redimensionamiento
        """
        if obj == getattr(self, "input_barcode", None):
            if event.type() == QEvent.MouseButtonPress:
                if not self.input_barcode.text().strip():
                    QTimer.singleShot(60, self._mostrar_todos_los_productos)
            elif event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_Down and not self.completer.popup().isVisible():
                    self._mostrar_todos_los_productos()
                    return True
        elif (obj is getattr(self, "_wm_card", None) or
              (hasattr(self, "tabla") and obj is self.tabla.viewport())) and event.type() == QEvent.Resize:
            self._reposicionar_watermark()
        return super().eventFilter(obj, event)

    def _on_completer_item_activated(self, index: QModelIndex):
        """Se activa al presionar Enter sobre una sugerencia o al hacer click en ella."""
        item = self._completer_model.itemFromIndex(index)
        if not item:
            return
        producto = item.data(Qt.UserRole)
        if not producto:
            return

        self._just_completed = True
        raw = self.input_barcode.text().strip()
        cantidad = Decimal("1")
        if "*" in raw:
            partes = raw.split("*", 1)
            try:
                cant_par = Decimal(partes[0].strip().replace(",", "."))
                if cant_par > 0:
                    cantidad = cant_par
            except Exception:
                pass

        self._agregar_producto(producto, cantidad=cantidad)
        QTimer.singleShot(10, self.input_barcode.clear)
        self._restaurar_foco_barcode()


    # ── Manejo de Código de Barras y Productos ────────────────────────────────

    def _agregar_por_barcode(self):
        if getattr(self, "_just_completed", False):
            self._just_completed = False
            return

        raw = self.input_barcode.text().strip()
        if not raw:
            return

        cantidad = Decimal("1")
        codigo = raw

        # Permite formato "3*7750123" o "2*codigo"
        if "*" in raw:
            partes = raw.split("*", 1)
            try:
                cant_par = Decimal(partes[0].strip().replace(",", "."))
                if cant_par > 0:
                    cantidad = cant_par
                    codigo = partes[1].strip()
            except Exception:
                pass

        codigo_limpio = normalizar_codigo_barras(codigo)
        producto = self.session.query(Producto).filter_by(codigo_barras=codigo_limpio, activo=True).first()
        if not producto and codigo != codigo_limpio:
            producto = self.session.query(Producto).filter_by(codigo_barras=codigo, activo=True).first()

        if not producto:
            # Intentar buscar por descripción exacta si no es numérico
            producto = self.session.query(Producto).filter(
                Producto.descripcion.ilike(f"%{codigo}%"),
                Producto.activo == True
            ).first()

        if not producto:
            self._set_status(f"⚠ Producto '{codigo}' no encontrado en catálogo.", "warning")
            es_admin = self.usuario.es_admin()
            if es_admin and len(codigo_limpio) >= 4:
                resp = QMessageBox.question(
                    self,
                    "Producto no registrado",
                    f"El producto con código '{codigo_limpio}' no está en el catálogo.\n\n"
                    f"¿Desea registrarlo ahora y agregarlo a la venta actual?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if resp == QMessageBox.Yes:
                    from ui.productos_widget import ProductoDialog
                    dlg = ProductoDialog(self.session, parent=self, codigo_inicial=codigo_limpio)
                    if dlg.exec():
                        self._actualizar_autocompletado()
                        nuevo_prod = self.session.query(Producto).filter_by(codigo_barras=codigo_limpio, activo=True).first()
                        if nuevo_prod:
                            self._agregar_producto(nuevo_prod, cantidad=cantidad)
                            self._set_status(f"✓ Registrado y agregado: {nuevo_prod.descripcion}", "success")
        else:
            self._agregar_producto(producto, cantidad=cantidad)

        self.input_barcode.clear()
        self._restaurar_foco_barcode()

    def _agregar_producto(self, producto: Producto, cantidad: Decimal = Decimal("1")):
        nueva_cant = cantidad
        for item in self._items:
            if item["producto"].id == producto.id:
                item["cantidad"] += cantidad
                nueva_cant = item["cantidad"]
                break
        else:
            self._items.append({"producto": producto, "cantidad": cantidad})
            nueva_cant = cantidad

        self._refrescar_tabla()

        # Aviso sobre el stock del producto
        st = producto.stock_actual
        st_txt = str(int(st)) if st == int(st) else f"{st:.3f}".rstrip('0').rstrip('.')
        if st <= Decimal("0"):
            self._set_status(f"⚠ ALERTA: '{producto.descripcion}' está AGOTADO en inventario.", "danger")
        elif nueva_cant > st:
            self._set_status(f"⚠ AVISO: Cantidad vendida ({nueva_cant}) supera el stock disponible ({st_txt} {producto.unidad_medida}).", "warning")
        elif producto.stock_bajo:
            self._set_status(f"⚠ AVISO: Stock bajo para '{producto.descripcion}' (Quedan: {st_txt} {producto.unidad_medida}).", "warning")
        else:
            self._set_status(f"✓ Agregado: {producto.descripcion} × {nueva_cant}", "success")

    def _cambiar_cantidad_item(self, index: int, delta: Decimal):
        if 0 <= index < len(self._items):
            nueva = self._items[index]["cantidad"] + delta
            if nueva <= Decimal("0"):
                self._eliminar_item(index)
            else:
                self._items[index]["cantidad"] = nueva
                self._refrescar_tabla()
        self._restaurar_foco_barcode()

    def _eliminar_item(self, index: int):
        if 0 <= index < len(self._items):
            nombre = self._items[index]["producto"].descripcion
            self._items.pop(index)
            self._refrescar_tabla()
            self._set_status(f"Eliminado: {nombre}", "muted")
        self._restaurar_foco_barcode()

    def _eliminar_fila_seleccionada(self):
        row = self.tabla.currentRow()
        if row >= 0:
            self._eliminar_item(row)

    def _refrescar_tabla(self):
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(self._items))
        total = Decimal("0.00")

        table_text = PALETTE.get("pos_table_text", "#000000")

        def _ro_item(text: str, font_size: int = 14, bold: bool = False, color: str = None) -> QTableWidgetItem:
            if color is None:
                color = table_text
            it = QTableWidgetItem(text)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            f = QFont("Segoe UI", font_size)
            if bold:
                f.setBold(True)
            it.setFont(f)
            it.setForeground(QColor(color))
            return it

        for i, item in enumerate(self._items):
            prod: Producto = item["producto"]
            cant: Decimal = item["cantidad"]
            subtotal = cant * prod.precio_venta_bs
            total += subtotal

            self.tabla.setRowHeight(i, 48)

            # Col 0: # (centrado, 14px)
            it_num = _ro_item(str(i + 1), font_size=14, bold=True)
            it_num.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, COL_NUM, it_num)

            # Col 1: Código (centrado, 14px)
            it_cod = _ro_item(prod.codigo_barras, font_size=14)
            it_cod.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, COL_CODIGO, it_cod)

            # Col 2: Descripción (legible, 14px, negrita)
            it_desc = _ro_item(prod.descripcion, font_size=14, bold=True)
            it_desc.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.tabla.setItem(i, COL_DESCRIPCION, it_desc)

            # Col 3: UM (centrado, 14px, negrita)
            it_um = _ro_item(prod.unidad_medida, font_size=14, bold=True)
            it_um.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, COL_UM, it_um)

            # Col 4: Cantidad con diseño amigable e intuitivo
            cant_container = QWidget()
            cant_container.setStyleSheet("background: transparent;")
            cw_lay = QHBoxLayout(cant_container)
            cw_lay.setContentsMargins(0, 0, 0, 0)
            cw_lay.setAlignment(Qt.AlignCenter)

            pill_frame = QFrame()
            pill_frame.setObjectName("pill_frame")
            pill_frame.setFixedHeight(34)
            pill_frame.setStyleSheet("""
                QFrame#pill_frame {
                    background-color: #f8fafc;
                    border: 1px solid #cbd5e1;
                    border-radius: 17px;
                }
            """)
            pill_lay = QHBoxLayout(pill_frame)
            pill_lay.setContentsMargins(5, 0, 5, 0)
            pill_lay.setSpacing(6)
            pill_lay.setAlignment(Qt.AlignCenter)

            btn_minus = QPushButton("−")
            btn_minus.setCursor(Qt.PointingHandCursor)
            btn_minus.setToolTip("Disminuir cantidad")
            btn_minus.setStyleSheet("""
                QPushButton {
                    width: 26px;
                    height: 26px;
                    min-width: 26px;
                    max-width: 26px;
                    min-height: 26px;
                    max-height: 26px;
                    padding: 0px;
                    margin: 0px;
                    background-color: #fee2e2;
                    color: #dc2626;
                    border: 1px solid #fca5a5;
                    border-radius: 13px;
                    font-size: 15px;
                    font-weight: bold;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: #ef4444;
                    color: #ffffff;
                    border-color: #ef4444;
                }
                QPushButton:pressed {
                    background-color: #b91c1c;
                }
            """)
            btn_minus.clicked.connect(lambda _, idx=i: self._cambiar_cantidad_item(idx, Decimal("-1")))
            pill_lay.addWidget(btn_minus, 0, Qt.AlignCenter)

            cant_txt = str(int(cant) if cant == int(cant) else f"{cant:.3f}")
            cant_label = QLabel(cant_txt)
            cant_label.setAlignment(Qt.AlignCenter)
            cant_label.setFixedHeight(26)
            cant_label.setStyleSheet(f"""
                font-size: 14px;
                font-weight: 900;
                color: {table_text};
                min-width: 28px;
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
            """)
            pill_lay.addWidget(cant_label, 0, Qt.AlignCenter)

            btn_plus = QPushButton("+")
            btn_plus.setCursor(Qt.PointingHandCursor)
            btn_plus.setToolTip("Aumentar cantidad")
            btn_plus.setStyleSheet("""
                QPushButton {
                    width: 26px;
                    height: 26px;
                    min-width: 26px;
                    max-width: 26px;
                    min-height: 26px;
                    max-height: 26px;
                    padding: 0px;
                    margin: 0px;
                    background-color: #dcfce7;
                    color: #16a34a;
                    border: 1px solid #86efac;
                    border-radius: 13px;
                    font-size: 15px;
                    font-weight: bold;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: #22c55e;
                    color: #ffffff;
                    border-color: #22c55e;
                }
                QPushButton:pressed {
                    background-color: #15803d;
                }
            """)
            btn_plus.clicked.connect(lambda _, idx=i: self._cambiar_cantidad_item(idx, Decimal("1")))
            pill_lay.addWidget(btn_plus, 0, Qt.AlignCenter)

            cw_lay.addWidget(pill_frame, 0, Qt.AlignCenter)
            self.tabla.setCellWidget(i, COL_CANTIDAD, cant_container)

            # Col 5: Precio Unitario (centrado, 14px)
            it_p = _ro_item(f"{prod.precio_venta_bs:.2f}", font_size=14)
            it_p.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, COL_PRECIO, it_p)

            # Col 6: Subtotal (centrado, 14px, negrita)
            it_sub = _ro_item(f"{subtotal:.2f}", font_size=14, bold=True)
            it_sub.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, COL_SUBTOTAL, it_sub)

            # Col 7: Botón Eliminar amigable y proporcionado (centrado)
            del_container = QWidget()
            del_container.setStyleSheet("background: transparent;")
            del_lay = QHBoxLayout(del_container)
            del_lay.setContentsMargins(0, 0, 0, 0)
            del_lay.setAlignment(Qt.AlignCenter)

            btn_del = QPushButton("✕")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setToolTip("Quitar producto")
            btn_del.setStyleSheet("""
                QPushButton {
                    width: 28px;
                    height: 28px;
                    min-width: 28px;
                    max-width: 28px;
                    min-height: 28px;
                    max-height: 28px;
                    padding: 0px;
                    margin: 0px;
                    background-color: #fee2e2;
                    color: #dc2626;
                    border: 1px solid #fca5a5;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: #ef4444;
                    color: #ffffff;
                    border-color: #ef4444;
                }
                QPushButton:pressed {
                    background-color: #b91c1c;
                }
            """)
            btn_del.clicked.connect(lambda _, idx=i: self._eliminar_item(idx))
            del_lay.addWidget(btn_del, 0, Qt.AlignCenter)
            self.tabla.setCellWidget(i, COL_ACCIONES, del_container)

        self._total_actual = total
        self.lbl_total.setText(f"{CURRENCY} {total:.2f}")

        n = len(self._items)
        unidades = sum(it["cantidad"] for it in self._items)
        if n == 0:
            self.lbl_items_count.setText("Carrito vacío")
            self.btn_cobrar.setEnabled(False)
            self.btn_cobrar.setText("COBRAR")
        else:
            self.lbl_items_count.setText(f"{n} producto(s)  ·  {unidades:.0f} unid.")
            self.btn_cobrar.setEnabled(True)
            self.btn_cobrar.setText(f"COBRAR — {CURRENCY} {total:.2f}")

        # Actualizar mini-resumen lateral
        self.lista_resumen.clear()
        for item in reversed(self._items[-4:]):
            p = item["producto"]
            c = item["cantidad"]
            c_txt = str(int(c) if c == int(c) else c)
            self.lista_resumen.addItem(f"• {p.descripcion[:22]}  ×{c_txt}")

        self.tabla.blockSignals(False)

    def _on_cell_changed(self, row: int, col: int):
        pass

    # ── Cliente ───────────────────────────────────────────────────────────────

    def _buscar_cliente(self):
        texto = self.input_nit.text().strip()
        if not texto:
            self._cliente = None
            self.lbl_cliente.setText("Público General  (Sin NIT)")
            self.lbl_cliente.setStyleSheet("color: #94a3b8; font-size: 14px; background: transparent; border: none;")
            return

        cliente = self.session.query(Cliente).filter(
            (Cliente.nit == texto) | (Cliente.razon_social.ilike(f"%{texto}%"))
        ).first()

        if cliente:
            self._cliente = cliente
            self.lbl_cliente.setText(f"✓ {cliente.razon_social} (NIT: {cliente.nit})")
            self.lbl_cliente.setStyleSheet(f"color: {PALETTE['success']}; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        else:
            self._cliente = None
            self.lbl_cliente.setText("⚠ Cliente no encontrado (Público General)")
            self.lbl_cliente.setStyleSheet(f"color: {PALETTE['warning']}; font-size: 14px; background: transparent; border: none;")

        self._restaurar_foco_barcode()

    def _abrir_buscar(self):
        dlg = BuscarProductoDialog(self.session, self)
        dlg.producto_seleccionado.connect(self._agregar_producto)
        dlg.exec()
        self._restaurar_foco_barcode()

    # ── Control de Caja y Sesión Activa ───────────────────────────────────────

    def _verificar_caja_activa(self):
        """Consulta la base de datos para obtener la caja actualmente abierta y almacena sus datos en primitivas."""
        caja_encontrada = None
        try:
            with get_session() as session:
                caja_encontrada = obtener_caja_activa(session, self.usuario.id)
                if not caja_encontrada and self.usuario.es_admin() and not self.usuario.tiene_rol("cajero"):
                    caja_encontrada = obtener_caja_activa(session)

                if caja_encontrada:
                    self._caja_activa_id = caja_encontrada.id
                    self._caja_activa_turno = str(caja_encontrada.turno)
                    self._caja_activa_monto_inicial = Decimal(str(caja_encontrada.monto_inicial_bs))
                    self._sesion_caja_activa = caja_encontrada
                else:
                    self._caja_activa_id = None
                    self._caja_activa_turno = ""
                    self._caja_activa_monto_inicial = Decimal("0.00")
                    self._sesion_caja_activa = None
        except Exception:
            self._caja_activa_id = None
            self._sesion_caja_activa = None

        if hasattr(self, "badge_caja"):
            self._actualizar_badge_caja()

    def _actualizar_badge_caja(self):
        if not hasattr(self, "badge_caja"):
            return
        # Mostrar badge/botón para cajeros, admins y usuarios con doble rol

        if self._caja_activa_id:
            self.badge_caja.setText(
                f"🟢 Caja #{self._caja_activa_id} · Turno: {self._caja_activa_turno} · Base: {CURRENCY} {self._caja_activa_monto_inicial:.2f}"
            )
            self.badge_caja.setFixedHeight(36)
            self.badge_caja.setStyleSheet("""
                background: #f0fdf4;
                color: #15803d;
                border: 2px solid #16a34a;
                border-radius: 8px;
                padding: 4px 14px;
                font-size: 13px;
                font-weight: bold;
            """)
            self.badge_caja.show()
            self.btn_caja_accion.setText("🔒 Cerrar Caja")
            self.btn_caja_accion.setFixedHeight(36)
            self.btn_caja_accion.setStyleSheet("""
                QPushButton {
                    background: #dc2626;
                    color: #ffffff;
                    border: 2px solid #b91c1c;
                    border-radius: 8px;
                    padding: 4px 16px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #ef4444;
                }
            """)
            self.btn_caja_accion.show()
        else:
            self.badge_caja.setText("🔴 Caja Cerrada")
            self.badge_caja.setFixedHeight(36)
            self.badge_caja.setStyleSheet("""
                background: #ffffff;
                color: #b91c1c;
                border: 2px solid #b91c1c;
                border-radius: 8px;
                padding: 4px 14px;
                font-size: 13px;
                font-weight: bold;
            """)
            self.badge_caja.show()
            self.btn_caja_accion.setText("🔓 Abrir Caja")
            self.btn_caja_accion.setFixedHeight(36)
            self.btn_caja_accion.setStyleSheet("""
                QPushButton {
                    background: #0f172a;
                    color: #ffffff;
                    border: 2px solid #000000;
                    border-radius: 8px;
                    padding: 4px 16px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #2563eb;
                    border-color: #2563eb;
                }
            """)
            self.btn_caja_accion.show()

    def _gestionar_caja(self):
        # Disponible para cajeros, admins y usuarios con doble rol (admin+cajero)
        self._verificar_caja_activa()
        if not self._caja_activa_id:
            self._abrir_formulario_apertura()
        else:
            self._abrir_formulario_cierre()

    def _abrir_formulario_apertura(self):
        dlg = AperturaCajaDialog(self.usuario, self)
        if dlg.exec() == QDialog.Accepted:
            self._verificar_caja_activa()
            if self._caja_activa_id:
                self._set_status(f"✓ Caja abierta para el turno {self._caja_activa_turno}.", "success")
        self._restaurar_foco_barcode()

    def _abrir_formulario_cierre(self):
        if not self._caja_activa_id:
            return
        dlg = CierreCajaDialog(self._caja_activa_id, self)
        if dlg.exec() == QDialog.Accepted:
            self._verificar_caja_activa()
            self._set_status("✓ Caja cerrada. Arqueo finalizado con éxito.", "info")
        self._restaurar_foco_barcode()

    def _actualizar_badge_qr(self):
        """Actualiza el botón superior del QR según si el usuario tiene una imagen QR activa."""
        if not hasattr(self, "btn_mi_qr"):
            return

        tiene_qr = False
        try:
            with get_session() as s:
                u = s.get(Usuario, self.usuario.id)
                if u and u.qr_imagen:
                    tiene_qr = (resolver_ruta(u.qr_imagen) is not None)
                    self.usuario.qr_imagen = u.qr_imagen
        except Exception:
            pass

        if tiene_qr:
            self.btn_mi_qr.setText("📱 Mi QR (🟢)")
            self.btn_mi_qr.setToolTip("Código QR activo y configurado. Clic para ver o cambiar.")
            self.btn_mi_qr.setFixedHeight(36)
            self.btn_mi_qr.setStyleSheet("""
                QPushButton {
                    background: #f0fdf4;
                    color: #15803d;
                    border: 2px solid #16a34a;
                    border-radius: 8px;
                    padding: 4px 14px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #dcfce7;
                    border-color: #15803d;
                }
            """)
        else:
            self.btn_mi_qr.setText("📱 Subir QR (⚠️)")
            self.btn_mi_qr.setToolTip("No has subido tu código QR personal para cobrar. Haz clic aquí para subirlo.")
            self.btn_mi_qr.setFixedHeight(36)
            self.btn_mi_qr.setStyleSheet("""
                QPushButton {
                    background: #fffbeb;
                    color: #b45309;
                    border: 2px solid #f59e0b;
                    border-radius: 8px;
                    padding: 4px 14px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #fef3c7;
                    border-color: #d97706;
                }
            """)

    def _abrir_gestion_qr(self):
        """Abre el diálogo modal de gestión del código QR del cajero actual."""
        dlg = GestionQRDialog(self.usuario.id, parent=self)
        dlg.exec()
        self._actualizar_badge_qr()
        self._restaurar_foco_barcode()

    def actualizar(self):
        """Método invocado al entrar a la pestaña del POS desde la barra lateral."""
        self._verificar_caja_activa()
        self._actualizar_badge_qr()
        self._actualizar_autocompletado()
        self._reposicionar_watermark()
        self._restaurar_foco_barcode()

    # ── Cobro y Flujo de Caja ─────────────────────────────────────────────────

    def _abrir_cobro(self):
        try:
            if not self._items:
                self._set_status("⚠ Debe agregar productos al carrito antes de cobrar.", "warning")
                return

            # Validar si la caja está abierta antes de cobrar (obligatorio para cajeros y admin+cajero)
            self._verificar_caja_activa()
            necesita_caja = self.usuario.tiene_rol("cajero") or self.usuario.tiene_rol("admin")
            if necesita_caja and not self._caja_activa_id:
                from ui.caja_dialog import ConfirmarAperturaPromptDialog
                dlg_prompt = ConfirmarAperturaPromptDialog(self.usuario, self)
                if dlg_prompt.exec() == QDialog.Accepted:
                    self._abrir_formulario_apertura()
                if not self._caja_activa_id:
                    self._set_status("⚠ Venta en espera: Caja cerrada.", "warning")
                    return

            sesion_id = self._caja_activa_id
            dlg = CobrarDialog(
                total=self._total_actual,
                session=self.session,
                items=self._items,
                usuario=self.usuario,
                cliente=self._cliente,
                sesion_caja_id=sesion_id,
                parent=self,
            )

            if dlg.exec() == QDialog.Accepted:
                v_info = dlg.venta_registrada
                pdf_path = dlg.pdf_path
                try:
                    self.session.expire_all()
                except Exception:
                    pass

                # Mostrar pantalla de venta completada con Vuelto prominente
                exito_dlg = CobroExitosoDialog(
                    venta_info=v_info,
                    pdf_path=pdf_path,
                    parent=self
                )
                exito_dlg.exec()

                # Guardar en memoria y actualizar bloque persistente de última venta
                self._ultima_venta = v_info
                self._ultimo_ticket_pdf = pdf_path
                self._actualizar_bloque_ultima_venta()

                # Limpiar carrito para el siguiente cliente
                self._limpiar_items()
                self._actualizar_autocompletado()
                self._set_status("✓ Caja lista para el siguiente cliente.", "success")
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "Error en Cobro",
                f"Ocurrió un error inesperado al procesar el cobro:\n\n{e}"
            )

    def _actualizar_bloque_ultima_venta(self):
        if not self._ultima_venta:
            return

        v = self._ultima_venta
        if v.get("metodo") == "mixto":
            metodo_str = f"Mixto (QR: {CURRENCY} {v.get('monto_qr', Decimal('0')):.2f} + Efec: {CURRENCY} {v.get('monto_efectivo', Decimal('0')):.2f})"
        else:
            metodo_str = v.get("metodo", "").capitalize()
        vuelto_txt = f" | Vuelto: {CURRENCY} {v['vuelto']:.2f}" if v["vuelto"] > 0 else ""
        self.lbl_uv_info.setText(
            f"<b>Venta #{v['numero']:06d}</b><br>"
            f"Total: <b>{CURRENCY} {v['total']:.2f}</b> ({metodo_str})<br>"
            f"{vuelto_txt}"
        )
        self.lbl_uv_info.setStyleSheet("color: #e2e8f0; font-size: 14px; background: transparent; border: none;")
        if self._ultimo_ticket_pdf:
            self.btn_reimprimir_ticket.show()

    def _reimprimir_ultimo_ticket(self):
        if self._ultimo_ticket_pdf and Path(self._ultimo_ticket_pdf).exists():
            try:
                os.startfile(str(self._ultimo_ticket_pdf))
            except Exception as e:
                QMessageBox.information(self, "Ticket", f"Ruta del ticket:\n{self._ultimo_ticket_pdf}")
        else:
            QMessageBox.warning(self, "Ticket", "El ticket no se encuentra disponible.")

    def _limpiar_venta(self):
        if self._items:
            resp = QMessageBox.question(
                self, "Cancelar venta",
                "¿Desea cancelar la venta en curso?\nSe limpiará el carrito.",
                QMessageBox.Yes | QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                self._restaurar_foco_barcode()
                return

        self._limpiar_items()
        self._set_status("Venta cancelada.", "muted")

    def _limpiar_items(self):
        self._items.clear()
        self._total_actual = Decimal("0.00")
        self._cliente = None
        self.input_nit.clear()
        self.lbl_cliente.setText("Público General  (Sin NIT)")
        self.lbl_cliente.setStyleSheet("color: #94a3b8; font-size: 14px; background: transparent; border: none;")
        self._refrescar_tabla()
        self._restaurar_foco_barcode()

    def _set_status(self, texto: str, tipo: str = "muted"):
        colores = {
            "success": PALETTE["success"],
            "warning": PALETTE["warning"],
            "danger":  PALETTE["danger"],
            "muted":   "#cbd5e1",
        }
        c = colores.get(tipo, "#cbd5e1")
        self.lbl_status.setStyleSheet(f"color: {c}; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        self.lbl_status.setText(texto)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposicionar_watermark()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(10, self._reposicionar_watermark)
        QTimer.singleShot(80, self._reposicionar_watermark)

    def _actualizar_pixmap_watermark(self, max_w: int = 800, max_h: int = 580):
        """Genera el pixmap semi-transparente del logo escalado al tamaño óptimo."""
        if not getattr(self, "_wm_orig_pix", None) or self._wm_orig_pix.isNull():
            return
        scaled_size = self._wm_orig_pix.scaled(max_w, max_h, Qt.KeepAspectRatio).size()
        current_pix = self._wm_label.pixmap() if hasattr(self, "_wm_label") else None
        if (getattr(self, "_wm_pix_size", None) == scaled_size and
                current_pix is not None and not current_pix.isNull()):
            return

        scaled = self._wm_orig_pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if scaled.isNull():
            return

        pix_wm = QPixmap(scaled.size())
        pix_wm.fill(Qt.transparent)
        painter = QPainter(pix_wm)
        painter.setOpacity(0.20)  # 20% de opacidad → perfectamente visible, nítido y legible
        painter.drawPixmap(0, 0, scaled)
        painter.end()

        self._wm_label.setPixmap(pix_wm)
        self._wm_pix_size = pix_wm.size()

    def _reposicionar_watermark(self):
        """Centra el QLabel de marca de agua con precisión matemática y óptica dentro de la tabla de productos,
        alineado exactamente con el área visible de datos (viewport) y compensando el asa del carrito."""
        if not hasattr(self, "_wm_label") or not hasattr(self, "_wm_card"):
            return
        card = self._wm_card
        lbl = self._wm_label
        if not hasattr(self, "tabla") or not self.tabla.viewport():
            return

        vp = self.tabla.viewport()
        vw = vp.width()
        vh = vp.height()
        if vw <= 10 or vh <= 10:
            return

        # Coordenadas exactas del viewport mapeadas a table_card
        origin = vp.mapTo(card, QPoint(0, 0))
        ox = origin.x()
        oy = origin.y()

        # Tamaño deseado: hasta 800x580, ajustándose suavemente si el viewport es menor
        max_w = min(650, max(200, vw - 40))
        max_h = min(580, max(150, vh - 20))

        self._actualizar_pixmap_watermark(max_w, max_h)

        if getattr(self, "_wm_pix_size", None):
            lw = self._wm_pix_size.width()
            lh = self._wm_pix_size.height()
        else:
            lw, lh = max_w, max_h

        # Compensación óptica: el asa del carrito en el extremo izquierdo empuja el texto
        # principal ("Peke MARKET") hacia la derecha. Desplazamos levemente a la izquierda (~8.5%)
        # para que el centro visual del texto y el cuerpo del carrito coincidan con el centro de la tabla.
        optical_shift = int(lw * 0.085)

        # Centrado horizontal óptico dentro del área de la tabla
        raw_x = ox + (vw - lw) // 2 - optical_shift
        x = max(ox + 10, raw_x)

        # Centrado vertical exacto dentro del área visible de filas (debajo del encabezado)
        y = oy + max(0, (vh - lh) // 2)

        lbl.setGeometry(x, y, lw, lh)
        lbl.raise_()

    def closeEvent(self, event):
        self.session.close()
        super().closeEvent(event)
