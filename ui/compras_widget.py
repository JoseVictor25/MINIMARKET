"""
ui/compras_widget.py – Registro de compras a proveedores.
"""
from __future__ import annotations

import os
import calendar
from datetime import datetime, date
from decimal import Decimal

from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QFormLayout, QComboBox,
    QDoubleSpinBox, QMessageBox, QAbstractItemView,
    QFrame, QTextEdit, QSplitter, QDateEdit, QFileDialog,
)

from database import SessionLocal
from models.compra import Compra, DetalleCompra
from models.producto import Producto
from models.proveedor import Proveedor
from models.usuario import Usuario
from services.compra_service import registrar_compra
from services.export_service import exportar_compras_excel, exportar_compras_pdf
from config import CURRENCY, APP_NAME
from ui.styles import PALETTE, configurar_calendario_elegante


class NuevaCompraDialog(QDialog):
    """Formulario completo para registrar una nueva compra con entrada manual de cantidad y precio."""

    def __init__(self, usuario: Usuario = None, session=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # Manejo flexible de parámetros por si se llama (session, usuario) o (usuario, session)
        from sqlalchemy.orm import Session as SASession
        if isinstance(usuario, SASession):
            real_session = usuario
            real_usuario = session
        else:
            real_session = session
            real_usuario = usuario

        self.usuario = real_usuario
        self._propia_sesion = real_session is None
        self.session = real_session if real_session is not None else SessionLocal()
        self._items: list[dict] = []
        self.setWindowTitle("Registrar Compra")
        self.setMinimumSize(820, 580)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(18, 18, 18, 18)

        # ── Encabezado de la factura ─────────────────────────────────────────
        grp = QFrame()
        grp.setObjectName("card")
        form = QFormLayout(grp)
        form.setSpacing(10)
        form.setContentsMargins(14, 14, 14, 14)

        self.combo_prov = QComboBox()
        self.combo_prov.setFixedHeight(34)
        proveedores = self.session.query(Proveedor).order_by(Proveedor.razon_social).all()
        for p in proveedores:
            self.combo_prov.addItem(f"{p.nit} – {p.razon_social}", p.id)
        form.addRow("Proveedor *", self.combo_prov)

        self.input_factura = QLineEdit()
        self.input_factura.setFixedHeight(34)
        self.input_factura.setPlaceholderText("Número de factura del proveedor")
        form.addRow("N° Factura *", self.input_factura)

        self.input_obs = QLineEdit()
        self.input_obs.setFixedHeight(34)
        self.input_obs.setPlaceholderText("Opcional")
        form.addRow("Observación", self.input_obs)

        root.addWidget(grp)

        # ── Agregar producto (Entrada Manual) ────────────────────────────────
        agregar_frame = QFrame()
        agregar_frame.setObjectName("card")
        agregar_lay = QHBoxLayout(agregar_frame)
        agregar_lay.setContentsMargins(14, 12, 14, 12)
        agregar_lay.setSpacing(10)

        lbl_prod = QLabel("Producto:")
        lbl_prod.setStyleSheet("font-weight: 600;")
        agregar_lay.addWidget(lbl_prod)

        self.combo_prod = QComboBox()
        self.combo_prod.setFixedHeight(34)
        self.combo_prod.setMinimumWidth(260)
        productos = self.session.query(Producto).filter_by(activo=True).order_by(Producto.descripcion).all()
        for p in productos:
            self.combo_prod.addItem(f"{p.codigo_barras} – {p.descripcion}", p.id)
        self.combo_prod.currentIndexChanged.connect(self._on_producto_cambiado)
        agregar_lay.addWidget(self.combo_prod, 1)

        lbl_cant = QLabel("Cant:")
        lbl_cant.setStyleSheet("font-weight: 600;")
        agregar_lay.addWidget(lbl_cant)

        self.input_cant = QLineEdit()
        self.input_cant.setFixedHeight(34)
        self.input_cant.setFixedWidth(85)
        self.input_cant.setPlaceholderText("1")
        self.input_cant.setText("1")
        self.input_cant.setAlignment(Qt.AlignCenter)
        self.input_cant.setStyleSheet("""
            QLineEdit {
                background-color: #1a2333;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                border: 1.5px solid #334155;
                border-radius: 6px;
                padding: 4px 6px;
            }
            QLineEdit:focus {
                border-color: #0ea5e9;
                background-color: #1f2b3e;
            }
        """)
        self.input_cant.returnPressed.connect(lambda: self.input_precio.setFocus())
        agregar_lay.addWidget(self.input_cant)

        lbl_pr = QLabel(f"P. Compra {CURRENCY}:")
        lbl_pr.setStyleSheet("font-weight: 600;")
        agregar_lay.addWidget(lbl_pr)

        self.input_precio = QLineEdit()
        self.input_precio.setFixedHeight(34)
        self.input_precio.setFixedWidth(105)
        self.input_precio.setPlaceholderText("0.00")
        self.input_precio.setAlignment(Qt.AlignRight)
        self.input_precio.setStyleSheet("""
            QLineEdit {
                background-color: #1a2333;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                border: 1.5px solid #334155;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QLineEdit:focus {
                border-color: #0ea5e9;
                background-color: #1f2b3e;
            }
        """)
        self.input_precio.returnPressed.connect(self._agregar_item)
        agregar_lay.addWidget(self.input_precio)

        btn_agregar = QPushButton("+ Agregar")
        btn_agregar.setObjectName("btn_primary")
        btn_agregar.setCursor(Qt.PointingHandCursor)
        btn_agregar.setFixedHeight(34)
        btn_agregar.setStyleSheet("""
            QPushButton {
                background-color: #0ea5e9;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #38bdf8;
            }
            QPushButton:pressed {
                background-color: #0284c7;
            }
        """)
        btn_agregar.clicked.connect(self._agregar_item)
        agregar_lay.addWidget(btn_agregar)

        root.addWidget(agregar_frame)

        # Cargar precio inicial del primer producto
        self._on_producto_cambiado()

        # ── Tabla de detalle ──────────────────────────────────────────────────
        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels(
            ["Código", "Descripción", "Cantidad", f"P. Compra {CURRENCY}", f"Subtotal {CURRENCY}", "Acción"]
        )
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.setColumnWidth(0, 110)
        self.tabla.setColumnWidth(2, 95)
        self.tabla.setColumnWidth(3, 115)
        self.tabla.setColumnWidth(4, 120)
        self.tabla.setColumnWidth(5, 85)
        header.setFixedHeight(38)

        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(36)
        root.addWidget(self.tabla, 1)

        # ── Total y botones ──────────────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.setContentsMargins(4, 4, 4, 4)

        self.lbl_total = QLabel(f"Total: {CURRENCY} 0.00")
        self.lbl_total.setStyleSheet(f"font-size: 19px; font-weight: bold; color: {PALETTE['success']};")
        bottom.addWidget(self.lbl_total)
        bottom.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setFixedHeight(38)
        btn_cancel.setFixedWidth(100)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_cancel)

        btn_guardar = QPushButton("✓ Registrar Compra")
        btn_guardar.setObjectName("btn_success")
        btn_guardar.setFixedHeight(38)
        btn_guardar.setCursor(Qt.PointingHandCursor)
        btn_guardar.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #059669, stop:1 #047857);
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #34d399;
                border-radius: 6px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background: #10b981;
            }
        """)
        btn_guardar.clicked.connect(self._guardar)
        bottom.addWidget(btn_guardar)

        root.addLayout(bottom)

    def _on_producto_cambiado(self):
        """Rellena el precio con el costo actual del producto para mayor agilidad."""
        prod_id = self.combo_prod.currentData()
        if prod_id:
            prod = self.session.get(Producto, prod_id)
            if prod and prod.precio_compra_bs is not None:
                self.input_precio.setText(f"{prod.precio_compra_bs:.2f}")

    def _agregar_item(self):
        prod_id = self.combo_prod.currentData()
        if not prod_id:
            QMessageBox.warning(self, "Producto Requerido", "Seleccione un producto.")
            return

        prod = self.session.get(Producto, prod_id)
        if not prod:
            QMessageBox.warning(self, "Error", "Producto no encontrado.")
            return

        cant_txt = self.input_cant.text().strip().replace(",", ".")
        precio_txt = self.input_precio.text().strip().replace(",", ".")

        try:
            cant = Decimal(cant_txt) if cant_txt else Decimal("1")
            if cant <= 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "Cantidad Inválida", "Ingrese una cantidad numérica válida mayor a 0 (ej. 1, 10, 2.5).")
            self.input_cant.setFocus()
            self.input_cant.selectAll()
            return

        try:
            precio = Decimal(precio_txt) if precio_txt else Decimal("0")
            if precio <= 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "Precio Inválido", f"Ingrese un precio de compra válido mayor a 0 (ej. 15.00, 20.50).")
            self.input_precio.setFocus()
            self.input_precio.selectAll()
            return

        # Actualizar si ya existe en la lista de compra actual
        for item in self._items:
            if item["producto"].id == prod.id:
                item["cantidad"] += cant
                item["precio_unitario_bs"] = precio  # Toma el precio más reciente
                self._refrescar_tabla()
                self.input_cant.setText("1")
                self.input_cant.setFocus()
                self.input_cant.selectAll()
                return

        self._items.append({"producto": prod, "cantidad": cant, "precio_unitario_bs": precio})
        self._refrescar_tabla()

        # Preparar para siguiente entrada
        self.input_cant.setText("1")
        self.input_cant.setFocus()
        self.input_cant.selectAll()

    def _eliminar_item(self, idx: int):
        if 0 <= idx < len(self._items):
            del self._items[idx]
            self._refrescar_tabla()

    def _refrescar_tabla(self):
        self.tabla.setRowCount(len(self._items))
        total = Decimal("0.00")
        for i, item in enumerate(self._items):
            p = item["producto"]
            c = item["cantidad"]
            pr = item["precio_unitario_bs"]
            sub = c * pr
            total += sub

            cant_str = str(int(c)) if c == int(c) else f"{c:.3f}".rstrip('0').rstrip('.')

            it_cod = QTableWidgetItem(p.codigo_barras)
            it_cod.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, 0, it_cod)

            it_desc = QTableWidgetItem(p.descripcion)
            self.tabla.setItem(i, 1, it_desc)

            it_cant = QTableWidgetItem(cant_str)
            it_cant.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, 2, it_cant)

            it_pr = QTableWidgetItem(f"{pr:.2f}")
            it_pr.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla.setItem(i, 3, it_pr)

            it_sub = QTableWidgetItem(f"{sub:.2f}")
            it_sub.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla.setItem(i, 4, it_sub)

            # Botón de eliminar
            btn_quitar = QPushButton("✕")
            btn_quitar.setToolTip("Quitar producto de la lista")
            btn_quitar.setCursor(Qt.PointingHandCursor)
            btn_quitar.setFixedHeight(24)
            btn_quitar.setFixedWidth(32)
            btn_quitar.setStyleSheet("""
                QPushButton {
                    background-color: rgba(239, 68, 68, 0.2);
                    color: #f87171;
                    border: 1px solid #ef4444;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                    padding: 0px;
                    margin: 0px;
                }
                QPushButton:hover {
                    background-color: #ef4444;
                    color: #ffffff;
                }
            """)
            btn_quitar.clicked.connect(lambda _, row=i: self._eliminar_item(row))

            c_widget = QWidget()
            c_lay = QHBoxLayout(c_widget)
            c_lay.setContentsMargins(0, 0, 0, 0)
            c_lay.setAlignment(Qt.AlignCenter)
            c_lay.addWidget(btn_quitar)
            self.tabla.setCellWidget(i, 5, c_widget)

        self.lbl_total.setText(f"Total: {CURRENCY} {total:.2f}")

    def _guardar(self):
        if not self._items:
            QMessageBox.warning(self, "Sin Productos", "Agregue al menos un producto a la compra.")
            return

        num_factura = self.input_factura.text().strip()
        if not num_factura:
            QMessageBox.warning(self, "Factura Requerida", "Ingrese el número de factura del proveedor.")
            self.input_factura.setFocus()
            return

        prov_id = self.combo_prov.currentData()
        if not prov_id:
            QMessageBox.warning(self, "Proveedor Requerido", "Seleccione un proveedor.")
            return

        prov = self.session.get(Proveedor, prov_id)
        usuario = None
        if self.usuario and hasattr(self.usuario, "id"):
            usuario = self.session.get(Usuario, self.usuario.id)
        if not usuario:
            usuario = self.session.query(Usuario).first()

        try:
            # Refrescar productos en la sesión activa
            items_frescos = []
            for item in self._items:
                prod = self.session.get(Producto, item["producto"].id)
                items_frescos.append({
                    "producto": prod,
                    "cantidad": item["cantidad"],
                    "precio_unitario_bs": item["precio_unitario_bs"],
                })

            registrar_compra(
                session=self.session,
                usuario=usuario,
                proveedor=prov,
                numero_factura=num_factura,
                items=items_frescos,
                observacion=self.input_obs.text().strip() or None,
            )
            self.session.commit()
            QMessageBox.information(
                self,
                "Compra Registrada",
                f"La compra con factura N° {num_factura} fue registrada exitosamente.\n"
                f"Se actualizó el stock y los precios de compra de los productos."
            )
            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "Error al Registrar Compra", f"No se pudo registrar la compra:\n{e}")

    def closeEvent(self, event):
        if self._propia_sesion:
            self.session.close()
        super().closeEvent(event)


def _crear_kpi_card(titulo: str, valor_init: str, color_hex: str, subtexto: str = "") -> tuple[QFrame, QLabel, QLabel]:
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet("""
        QFrame#card {
            background-color: #1e293b;
            border: 1px solid #334155;
            border-radius: 10px;
        }
    """)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 12, 16, 12)
    lay.setSpacing(4)

    lbl_t = QLabel(titulo)
    lbl_t.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;")

    lbl_v = QLabel(valor_init)
    lbl_v.setStyleSheet(f"color: {color_hex}; font-size: 20px; font-weight: bold;")

    lbl_s = QLabel(subtexto)
    lbl_s.setStyleSheet("color: #64748b; font-size: 11px;")

    lay.addWidget(lbl_t)
    lay.addWidget(lbl_v)
    if subtexto:
        lay.addWidget(lbl_s)

    return card, lbl_v, lbl_s


class DetalleCompraDialog(QDialog):
    """Muestra el detalle completo de una compra registrada."""

    def __init__(self, compra: Compra, parent=None):
        super().__init__(parent)
        self.compra = compra
        self.setWindowTitle(f"Detalle de Compra – Factura #{compra.numero_factura}")
        self.setMinimumSize(720, 520)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        c = self.compra
        prov_nom = c.proveedor.razon_social if c.proveedor else "Sin proveedor"
        prov_nit = c.proveedor.nit if c.proveedor else "-"
        usuario_nom = c.usuario.username if c.usuario else "-"

        # Cabecera
        card_hdr = QFrame()
        card_hdr.setObjectName("card")
        card_hdr.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 8px;")
        card_hdr_lay = QVBoxLayout(card_hdr)
        card_hdr_lay.setContentsMargins(16, 14, 16, 14)
        card_hdr_lay.setSpacing(6)

        info_html = (
            f"<div style='font-size: 15px; color: #ffffff;'><b>Factura N°:</b> <span style='color: #38bdf8;'>{c.numero_factura}</span> &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Fecha:</b> {c.fecha.strftime('%d/%m/%Y %H:%M')}</div>"
            f"<div style='font-size: 13px; color: #94a3b8; margin-top: 6px; line-height: 1.4;'>"
            f"<b>Proveedor:</b> <span style='color: #f1f5f9; font-weight: 600;'>{prov_nom}</span> &nbsp; (NIT: {prov_nit})<br>"
            f"<b>Registrado por:</b> <span style='color: #f1f5f9;'>{usuario_nom}</span>"
        )
        if c.observacion:
            info_html += f"<br><b>Observación:</b> <i style='color: #cbd5e1;'>{c.observacion}</i>"
        info_html += "</div>"

        lbl_info = QLabel(info_html)
        lbl_info.setTextFormat(Qt.RichText)
        card_hdr_lay.addWidget(lbl_info)
        lay.addWidget(card_hdr)

        # Subtítulo de artículos
        lbl_art = QLabel("Detalle de Productos Ingresados:")
        lbl_art.setStyleSheet("font-weight: bold; font-size: 13px; color: #f8fafc; margin-top: 4px;")
        lay.addWidget(lbl_art)

        # Tabla de artículos
        tabla = QTableWidget(len(c.detalles), 5)
        tabla.setHorizontalHeaderLabels(["Código", "Descripción", "Cantidad", f"P. Unit. {CURRENCY}", f"Subtotal {CURRENCY}"])
        tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tabla.verticalHeader().setVisible(False)
        tabla.setAlternatingRowColors(True)

        for i, d in enumerate(c.detalles):
            cod = d.producto.codigo_barras if d.producto else ""
            desc = d.producto.descripcion if d.producto else ""
            cant_str = str(int(d.cantidad)) if d.cantidad == int(d.cantidad) else f"{d.cantidad:.3f}".rstrip('0').rstrip('.')

            it_cod = QTableWidgetItem(cod)
            it_cod.setTextAlignment(Qt.AlignCenter)
            tabla.setItem(i, 0, it_cod)

            tabla.setItem(i, 1, QTableWidgetItem(desc))

            it_cant = QTableWidgetItem(cant_str)
            it_cant.setTextAlignment(Qt.AlignCenter)
            tabla.setItem(i, 2, it_cant)

            it_pr = QTableWidgetItem(f"{d.precio_unitario_bs:.2f}")
            it_pr.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tabla.setItem(i, 3, it_pr)

            it_sub = QTableWidgetItem(f"{d.subtotal_bs:.2f}")
            it_sub.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tabla.setItem(i, 4, it_sub)

        lay.addWidget(tabla, 1)

        # Total y Cerrar
        bot = QHBoxLayout()
        lbl_tot = QLabel(f"TOTAL COMPRA: {CURRENCY} {c.total_bs:.2f}")
        lbl_tot.setStyleSheet("font-size: 19px; font-weight: bold; color: #10b981;")
        bot.addWidget(lbl_tot)
        bot.addStretch()

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setFixedHeight(36)
        btn_cerrar.setFixedWidth(110)
        btn_cerrar.setCursor(Qt.PointingHandCursor)
        btn_cerrar.clicked.connect(self.accept)
        bot.addWidget(btn_cerrar)

        lay.addLayout(bot)


class ComprasWidget(QWidget):
    """Panel de historial y gestión de compras a proveedores con filtros avanzados y exportación."""

    def __init__(self, usuario: Usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.session = SessionLocal()
        self._compras_filtradas: list[Compra] = []
        self._build_ui()
        self._cargar_compras()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(14)

        # ── 1. Barra de Título y Botones Principales ─────────────────────────
        top_bar = QHBoxLayout()
        lbl_tit = QLabel("COMPRAS Y ABASTECIMIENTO")
        lbl_tit.setFont(QFont("Segoe UI", 15, QFont.Bold))
        lbl_tit.setStyleSheet("color: #ffffff; letter-spacing: 0.5px;")
        top_bar.addWidget(lbl_tit)
        top_bar.addStretch()

        # Botón Exportar Excel
        self.btn_export_excel = QPushButton("📊 Exportar Excel")
        self.btn_export_excel.setFixedHeight(36)
        self.btn_export_excel.setCursor(Qt.PointingHandCursor)
        self.btn_export_excel.setStyleSheet("""
            QPushButton {
                background-color: #065f46;
                color: #ffffff;
                border: 1.5px solid #10b981;
                border-radius: 6px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.btn_export_excel.clicked.connect(self._exportar_excel)
        top_bar.addWidget(self.btn_export_excel)

        # Botón Exportar PDF
        self.btn_export_pdf = QPushButton("📄 Exportar PDF")
        self.btn_export_pdf.setFixedHeight(36)
        self.btn_export_pdf.setCursor(Qt.PointingHandCursor)
        self.btn_export_pdf.setStyleSheet("""
            QPushButton {
                background-color: #9f1239;
                color: #ffffff;
                border: 1.5px solid #f43f5e;
                border-radius: 6px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #be123c;
            }
        """)
        self.btn_export_pdf.clicked.connect(self._exportar_pdf)
        top_bar.addWidget(self.btn_export_pdf)

        # Botón + Nueva Compra
        self.btn_nueva = QPushButton("+ Nueva Compra")
        self.btn_nueva.setFixedHeight(36)
        self.btn_nueva.setCursor(Qt.PointingHandCursor)
        self.btn_nueva.setStyleSheet("""
            QPushButton {
                background-color: #0ea5e9;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 0 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #38bdf8;
            }
        """)
        self.btn_nueva.clicked.connect(self._nueva_compra)
        top_bar.addWidget(self.btn_nueva)

        lay.addLayout(top_bar)

        # ── 2. Tarjetas Resumen (KPIs) ───────────────────────────────────────
        kpis_lay = QHBoxLayout()
        kpis_lay.setSpacing(14)

        card1, self.lbl_kpi_total, self.lbl_kpi_total_sub = _crear_kpi_card("Total Invertido en Compras", f"{CURRENCY} 0.00", "#10b981", "En el período seleccionado")
        card2, self.lbl_kpi_cant, self.lbl_kpi_cant_sub = _crear_kpi_card("Facturas / Compras", "0", "#38bdf8", "Transacciones registradas")
        card3, self.lbl_kpi_provs, self.lbl_kpi_provs_sub = _crear_kpi_card("Proveedores Atendidos", "0", "#a855f7", "Diferentes proveedores")

        kpis_lay.addWidget(card1)
        kpis_lay.addWidget(card2)
        kpis_lay.addWidget(card3)
        lay.addLayout(kpis_lay)

        # ── 3. Barra de Filtros (Día, Mes, Año, Búsqueda) ────────────────────
        filter_frame = QFrame()
        filter_frame.setObjectName("card")
        filter_frame.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 8px;")
        filter_lay = QHBoxLayout(filter_frame)
        filter_lay.setContentsMargins(14, 10, 14, 10)
        filter_lay.setSpacing(10)

        lbl_filtro = QLabel("Filtrar por:")
        lbl_filtro.setStyleSheet("font-weight: bold; color: #e2e8f0; font-size: 13px;")
        filter_lay.addWidget(lbl_filtro)

        self.combo_periodo = QComboBox()
        self.combo_periodo.setFixedHeight(34)
        self.combo_periodo.addItems([
            "Todos los registros",
            "Hoy",
            "Por Día",
            "Por Mes",
            "Por Año",
        ])
        self.combo_periodo.currentIndexChanged.connect(self._on_periodo_cambiado)
        filter_lay.addWidget(self.combo_periodo)

        # Date Picker para Día o Hoy
        self.date_picker = QDateEdit()
        self.date_picker.setFixedHeight(34)
        self.date_picker.setFixedWidth(130)
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setDisplayFormat("dd/MM/yyyy")
        configurar_calendario_elegante(self.date_picker)
        self.date_picker.dateChanged.connect(lambda: self._cargar_compras())
        filter_lay.addWidget(self.date_picker)

        # Selector de Mes
        self.combo_mes = QComboBox()
        self.combo_mes.setFixedHeight(34)
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        self.combo_mes.addItems(meses)
        self.combo_mes.setCurrentIndex(datetime.now().month - 1)
        self.combo_mes.currentIndexChanged.connect(lambda: self._cargar_compras())
        filter_lay.addWidget(self.combo_mes)

        # Selector de Año
        self.combo_anio = QComboBox()
        self.combo_anio.setFixedHeight(34)
        current_year = datetime.now().year
        for y in range(current_year - 5, current_year + 3):
            self.combo_anio.addItem(str(y))
        self.combo_anio.setCurrentText(str(current_year))
        self.combo_anio.currentIndexChanged.connect(lambda: self._cargar_compras())
        filter_lay.addWidget(self.combo_anio)

        filter_lay.addStretch()

        # Búsqueda rápida por texto
        self.input_buscar = QLineEdit()
        self.input_buscar.setFixedHeight(34)
        self.input_buscar.setFixedWidth(270)
        self.input_buscar.setPlaceholderText("🔍 Buscar factura, proveedor, usuario...")
        self.input_buscar.textChanged.connect(lambda: self._cargar_compras())
        filter_lay.addWidget(self.input_buscar)

        lay.addWidget(filter_frame)

        # ── 4. Tabla de Compras ──────────────────────────────────────────────
        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels([
            "ID", "N° Factura", "Proveedor", "Fecha y Hora", f"Total {CURRENCY}", "Registrado por", "Observación"
        ])
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabla.setColumnWidth(0, 65)
        self.tabla.setColumnWidth(1, 130)
        self.tabla.setColumnWidth(3, 145)
        self.tabla.setColumnWidth(4, 115)
        self.tabla.setColumnWidth(5, 125)
        self.tabla.setColumnWidth(6, 160)

        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.doubleClicked.connect(self._ver_detalle)
        lay.addWidget(self.tabla, 1)

        # ── 5. Barra Inferior de Acciones ────────────────────────────────────
        bot_bar = QHBoxLayout()
        self.btn_detalle = QPushButton("👁 Ver Detalle de Compra")
        self.btn_detalle.setFixedHeight(34)
        self.btn_detalle.setCursor(Qt.PointingHandCursor)
        self.btn_detalle.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: #ffffff;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 0 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #475569;
            }
        """)
        self.btn_detalle.clicked.connect(self._ver_detalle)
        bot_bar.addWidget(self.btn_detalle)

        bot_bar.addStretch()
        self.lbl_conteo = QLabel("Mostrando 0 compras")
        self.lbl_conteo.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 500;")
        bot_bar.addWidget(self.lbl_conteo)
        lay.addLayout(bot_bar)

        # Inicializar visibilidad de controles de filtro
        self._on_periodo_cambiado()

    def _on_periodo_cambiado(self):
        modo = self.combo_periodo.currentText()
        if modo == "Todos los registros":
            self.date_picker.hide()
            self.combo_mes.hide()
            self.combo_anio.hide()
        elif modo == "Hoy":
            self.date_picker.show()
            self.date_picker.setEnabled(False)
            self.date_picker.setDate(QDate.currentDate())
            self.combo_mes.hide()
            self.combo_anio.hide()
        elif modo in ("Por Día", "Por Día específico"):
            self.date_picker.show()
            self.date_picker.setEnabled(True)
            self.combo_mes.hide()
            self.combo_anio.hide()
        elif modo == "Por Mes":
            self.date_picker.hide()
            self.combo_mes.show()
            self.combo_anio.show()
        elif modo == "Por Año":
            self.date_picker.hide()
            self.combo_mes.hide()
            self.combo_anio.show()

        if hasattr(self, "tabla"):
            self._cargar_compras()

    def _obtener_fechas_filtro(self) -> tuple[datetime | None, datetime | None, str]:
        modo = self.combo_periodo.currentText()
        now = datetime.now()

        if modo == "Hoy":
            inicio = datetime(now.year, now.month, now.day, 0, 0, 0)
            fin = datetime(now.year, now.month, now.day, 23, 59, 59)
            return inicio, fin, f"Hoy ({inicio.strftime('%d/%m/%Y')})"

        elif modo in ("Por Día", "Por Día específico"):
            qdate = self.date_picker.date()
            d = date(qdate.year(), qdate.month(), qdate.day())
            inicio = datetime(d.year, d.month, d.day, 0, 0, 0)
            fin = datetime(d.year, d.month, d.day, 23, 59, 59)
            return inicio, fin, f"Día {inicio.strftime('%d/%m/%Y')}"

        elif modo == "Por Mes":
            mes = self.combo_mes.currentIndex() + 1
            anio = int(self.combo_anio.currentText())
            inicio = datetime(anio, mes, 1, 0, 0, 0)
            _, last_day = calendar.monthrange(anio, mes)
            fin = datetime(anio, mes, last_day, 23, 59, 59)
            mes_nom = self.combo_mes.currentText()
            return inicio, fin, f"{mes_nom} {anio}"

        elif modo == "Por Año":
            anio = int(self.combo_anio.currentText())
            inicio = datetime(anio, 1, 1, 0, 0, 0)
            fin = datetime(anio, 12, 31, 23, 59, 59)
            return inicio, fin, f"Año {anio}"

        else:
            return None, None, "Todos los registros"

    def _cargar_compras(self):
        inicio, fin, periodo_str = self._obtener_fechas_filtro()
        query = self.session.query(Compra)

        if inicio and fin:
            query = query.filter(Compra.fecha >= inicio, Compra.fecha <= fin)

        compras = query.order_by(Compra.fecha.desc()).all()

        # Filtrar por texto si hay búsqueda
        filtro_txt = self.input_buscar.text().strip().lower()
        if filtro_txt:
            compras = [
                c for c in compras
                if filtro_txt in str(c.id)
                or filtro_txt in c.numero_factura.lower()
                or (c.proveedor and filtro_txt in c.proveedor.razon_social.lower())
                or (c.proveedor and filtro_txt in (c.proveedor.nit or "").lower())
                or (c.usuario and filtro_txt in c.usuario.username.lower())
                or (c.observacion and filtro_txt in c.observacion.lower())
            ]

        self._compras_filtradas = compras

        # Actualizar Tarjetas KPI
        total_monto = sum((c.total_bs for c in compras), Decimal("0.00"))
        provs_unicos = len(set(c.proveedor_id for c in compras if c.proveedor_id))
        self.lbl_kpi_total.setText(f"{CURRENCY} {total_monto:,.2f}")
        self.lbl_kpi_cant.setText(f"{len(compras)} compras")
        self.lbl_kpi_provs.setText(f"{provs_unicos} proveedores")

        # Actualizar Tabla
        self.tabla.setRowCount(len(compras))
        for i, c in enumerate(compras):
            prov_nom = c.proveedor.razon_social if c.proveedor else "Sin proveedor"
            usr_nom = c.usuario.username if c.usuario else "-"

            it_id = QTableWidgetItem(str(c.id))
            it_id.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, 0, it_id)

            it_fac = QTableWidgetItem(c.numero_factura)
            it_fac.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, 1, it_fac)

            self.tabla.setItem(i, 2, QTableWidgetItem(prov_nom))

            it_fec = QTableWidgetItem(c.fecha.strftime("%d/%m/%Y %H:%M"))
            it_fec.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, 3, it_fec)

            it_tot = QTableWidgetItem(f"{c.total_bs:,.2f}")
            it_tot.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_tot.setForeground(QColor("#10b981"))
            font_b = it_tot.font()
            font_b.setBold(True)
            it_tot.setFont(font_b)
            self.tabla.setItem(i, 4, it_tot)

            it_usr = QTableWidgetItem(usr_nom)
            it_usr.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, 5, it_usr)

            self.tabla.setItem(i, 6, QTableWidgetItem(c.observacion or "-"))
            self.tabla.item(i, 0).setData(Qt.UserRole, c.id)

        self.lbl_conteo.setText(f"Mostrando {len(compras)} compra(s) | {periodo_str}")

    def _get_compra_seleccionada(self) -> Compra | None:
        row = self.tabla.currentRow()
        if row < 0:
            return None
        c_id = self.tabla.item(row, 0).data(Qt.UserRole)
        return self.session.get(Compra, c_id)

    def _ver_detalle(self):
        c = self._get_compra_seleccionada()
        if not c:
            QMessageBox.information(self, "Seleccionar", "Haga clic en una compra de la lista para ver su detalle.")
            return
        dlg = DetalleCompraDialog(c, parent=self)
        dlg.exec()

    def _nueva_compra(self):
        dlg = NuevaCompraDialog(usuario=self.usuario, parent=self)
        if dlg.exec():
            self.session.expire_all()
            self._cargar_compras()

    def _exportar_excel(self):
        if not self._compras_filtradas:
            QMessageBox.warning(self, "Sin Datos", "No hay compras registradas en el período seleccionado para exportar.")
            return

        _, _, periodo_str = self._obtener_fechas_filtro()
        def_name = f"compras_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Compras a Excel", def_name, "Archivos Excel (*.xlsx)")
        if not path:
            return

        try:
            exportar_compras_excel(self._compras_filtradas, path, periodo_str)
            res = QMessageBox.question(
                self, "Exportación Exitosa",
                f"El reporte de compras en Excel se guardó correctamente en:\n{path}\n\n¿Desea abrir el archivo ahora?",
                QMessageBox.Yes | QMessageBox.No
            )
            if res == QMessageBox.Yes:
                os.startfile(path)
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"No se pudo generar el archivo Excel:\n{e}")

    def _exportar_pdf(self):
        if not self._compras_filtradas:
            QMessageBox.warning(self, "Sin Datos", "No hay compras registradas en el período seleccionado para exportar.")
            return

        _, _, periodo_str = self._obtener_fechas_filtro()
        def_name = f"compras_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Compras a PDF", def_name, "Archivos PDF (*.pdf)")
        if not path:
            return

        try:
            exportar_compras_pdf(self._compras_filtradas, path, periodo_str)
            res = QMessageBox.question(
                self, "Exportación Exitosa",
                f"El reporte de compras en PDF se generó exitosamente en:\n{path}\n\n¿Desea abrir el documento ahora?",
                QMessageBox.Yes | QMessageBox.No
            )
            if res == QMessageBox.Yes:
                os.startfile(path)
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"No se pudo generar el archivo PDF:\n{e}")

    def closeEvent(self, event):
        self.session.close()
        super().closeEvent(event)
