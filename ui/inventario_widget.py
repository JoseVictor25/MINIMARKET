"""
ui/inventario_widget.py – Panel moderno y completo de Inventario, Ganancias y Alertas de Stock.

Características:
 - Tarjetas ejecutivas KPI: Inversión en inventario, valor de venta proyectado,
   ganancia potencial estimada, ganancias reales en ventas y alertas de stock crítico.
 - Pestaña 1: Inventario detallado con rentabilidad por producto (Costo, Venta, Ganancia Unit.,
   Margen % y Ganancia Potencial Total del stock).
 - Pestaña 2: Alertas de Stock y Sugerencias de Reposición (con cálculo de capital necesario).
 - Pestaña 3: Ganancias Reales obtenidas en Ventas (Ingresos, Costos, Margen y Top productos rentables).
 - Pestaña 4: Historial de Ajustes manuales (Entradas y Salidas).
 - Filtros dinámicos en tiempo real por búsqueda de texto, categoría y estado de stock.
"""
from __future__ import annotations

import os
from decimal import Decimal
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QBrush
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QFormLayout, QComboBox,
    QDoubleSpinBox, QMessageBox, QAbstractItemView,
    QFrame, QTabWidget, QGridLayout, QScrollArea,
    QFileDialog,
)

from database import SessionLocal
from models.ajuste_inventario import AjusteInventario
from models.producto import Producto
from models.usuario import Usuario
from models.categoria import Categoria
from models.venta import Venta, DetalleVenta
from services.inventario_service import ajustar_stock, productos_con_stock_bajo
from services.export_service import (
    exportar_productos_bajo_stock_excel,
    exportar_productos_bajo_stock_pdf,
)
from config import CURRENCY
from ui.styles import PALETTE


class AjusteDialog(QDialog):
    """Formulario premium para registrar un ajuste manual de inventario."""

    def __init__(self, session, usuario: Usuario, producto=None, parent=None):
        super().__init__(parent)
        self.session = session
        self.usuario = usuario
        self._producto_preseleccionado = producto
        self.setWindowTitle("Registrar Ajuste de Inventario")
        self.setMinimumWidth(540)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(24, 20, 24, 20)

        # Encabezado del diálogo
        lbl_head = QLabel("Ajuste Manual de Existencias")
        lbl_head.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {PALETTE['accent']};")
        lay.addWidget(lbl_head)

        lbl_desc = QLabel("Registre entradas o salidas extraordinarias (mermas, vencimientos, conteos físicos).")
        lbl_desc.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px;")
        lay.addWidget(lbl_desc)

        form_frame = QFrame()
        form_frame.setObjectName("card")
        form_lay = QFormLayout(form_frame)
        form_lay.setLabelAlignment(Qt.AlignRight)
        form_lay.setSpacing(14)
        form_lay.setContentsMargins(16, 16, 16, 16)

        # Combo producto
        self.combo_prod = QComboBox()
        self.combo_prod.setMinimumHeight(34)
        self._prods_cache = {}
        productos = self.session.query(Producto).filter_by(activo=True).order_by(Producto.descripcion).all()
        for p in productos:
            st_txt = str(int(p.stock_actual)) if p.stock_actual == int(p.stock_actual) else f"{p.stock_actual:.3f}".rstrip('0').rstrip('.')
            texto = f"{p.descripcion} (Cód: {p.codigo_barras}) — Stock: {st_txt} {p.unidad_medida}"
            self.combo_prod.addItem(texto, p.id)
            self._prods_cache[p.id] = p

        if self._producto_preseleccionado:
            idx = self.combo_prod.findData(self._producto_preseleccionado.id)
            if idx >= 0:
                self.combo_prod.setCurrentIndex(idx)
        self.combo_prod.currentIndexChanged.connect(self._actualizar_info_prod)
        form_lay.addRow("Producto *", self.combo_prod)

        # Label info de stock actual
        self.lbl_stock_info = QLabel("")
        self.lbl_stock_info.setStyleSheet(f"color: {PALETTE['accent']}; font-weight: bold; font-size: 12px;")
        form_lay.addRow("Stock Actual:", self.lbl_stock_info)

        # Tipo de ajuste
        self.combo_tipo = QComboBox()
        self.combo_tipo.setMinimumHeight(34)
        self.combo_tipo.addItem("➕ Entrada (Suma existencias al inventario)", AjusteInventario.TIPO_ENTRADA)
        self.combo_tipo.addItem("➖ Salida  (Resta existencias por daño/merma/ajuste)", AjusteInventario.TIPO_SALIDA)
        form_lay.addRow("Operación *", self.combo_tipo)

        # Cantidad manual ingresada por el usuario
        self.input_cant = QLineEdit()
        self.input_cant.setMinimumHeight(34)
        self.input_cant.setPlaceholderText("Ingrese cantidad a ajustar (ej: 1, 5, 10, 0.5)...")
        form_lay.addRow("Cantidad *", self.input_cant)

        # Motivo
        self.input_motivo = QLineEdit()
        self.input_motivo.setMinimumHeight(34)
        self.input_motivo.setPlaceholderText("Ej: Conteo físico, producto vencido, rotura, donación...")
        form_lay.addRow("Motivo *", self.input_motivo)

        lay.addWidget(form_frame)

        # Botones de pie
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setMinimumWidth(100)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("✓ Confirmar y Registrar")
        btn_save.setObjectName("btn_primary")
        btn_save.setMinimumWidth(180)
        btn_save.clicked.connect(self._guardar)
        btn_row.addWidget(btn_save)

        lay.addLayout(btn_row)
        self._actualizar_info_prod()

    def _actualizar_info_prod(self):
        prod_id = self.combo_prod.currentData()
        prod = self._prods_cache.get(prod_id)
        if prod:
            st_txt = str(int(prod.stock_actual)) if prod.stock_actual == int(prod.stock_actual) else f"{prod.stock_actual:.3f}".rstrip('0').rstrip('.')
            min_txt = str(int(prod.stock_minimo)) if prod.stock_minimo == int(prod.stock_minimo) else f"{prod.stock_minimo:.3f}".rstrip('0').rstrip('.')
            estado = "🔴 AGOTADO" if prod.stock_actual <= 0 else ("🟡 BAJO" if prod.stock_bajo else "🟢 NORMAL")
            self.lbl_stock_info.setText(f"{st_txt} {prod.unidad_medida}  (Mínimo configurado: {min_txt} {prod.unidad_medida})  [{estado}]")
        else:
            self.lbl_stock_info.setText("-")

    def _guardar(self):
        cant_str = self.input_cant.text().strip().replace(",", ".")
        if not cant_str:
            QMessageBox.warning(self, "Campo requerido", "Por favor ingrese la cantidad a ajustar.")
            self.input_cant.setFocus()
            return

        try:
            cant = Decimal(cant_str)
            if cant <= Decimal("0"):
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "Cantidad Inválida", "Por favor ingrese una cantidad numérica válida mayor a 0 (ej: 1, 5, 2.5).")
            self.input_cant.setFocus()
            return

        motivo = self.input_motivo.text().strip()
        if not motivo:
            QMessageBox.warning(self, "Campo requerido", "Por favor ingrese el motivo del ajuste.")
            self.input_motivo.setFocus()
            return

        prod_id = self.combo_prod.currentData()
        prod = self.session.get(Producto, prod_id)
        if not prod:
            QMessageBox.warning(self, "Error", "Producto no encontrado.")
            return

        tipo = self.combo_tipo.currentData()
        usuario = self.session.get(type(self.usuario), self.usuario.id)

        # Advertencia de stock negativo si es salida
        if tipo == AjusteInventario.TIPO_SALIDA and cant > prod.stock_actual:
            reply = QMessageBox.question(
                self,
                "Advertencia de Stock Negativo",
                f"La cantidad a retirar ({cant}) supera el stock actual ({prod.stock_actual:.3f}).\n"
                f"¿Desea continuar de todas formas?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        try:
            ajustar_stock(self.session, usuario, prod, cant, tipo, motivo)
            self.session.commit()
            QMessageBox.information(self, "Ajuste Exitoso", "El ajuste de stock fue registrado correctamente.")
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Validación", str(e))
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "Error", f"No se pudo registrar el ajuste: {e}")


class InventarioWidget(QWidget):
    """Panel de inventario, ganancias y alertas de stock con diseño ejecutivo."""

    datos_actualizados = pyqtSignal(str)

    def __init__(self, usuario: Usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.session = SessionLocal()
        self._productos_cache: list[Producto] = []
        self._build_ui()
        self.actualizar()

    def _build_ui(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(20, 16, 20, 16)
        main_lay.setSpacing(14)

        # ── 1. Encabezado principal ──────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        titulos_box = QVBoxLayout()
        titulos_box.setSpacing(2)
        lbl_titulo = QLabel("Gestión de Inventario & Rentabilidad")
        lbl_titulo.setObjectName("title")
        titulos_box.addWidget(lbl_titulo)

        lbl_sub = QLabel("Control de existencias físicas, cálculo de ganancias proyectadas y alertas de reposición")
        lbl_sub.setObjectName("label_small")
        titulos_box.addWidget(lbl_sub)
        hdr.addLayout(titulos_box)

        hdr.addStretch()

        btn_exp_pdf = QPushButton("📄 Exportar PDF")
        btn_exp_pdf.setCursor(Qt.PointingHandCursor)
        btn_exp_pdf.setToolTip("Exportar a PDF los productos con stock actual menor o igual al mínimo")
        btn_exp_pdf.clicked.connect(self._exportar_bajo_stock_pdf)
        hdr.addWidget(btn_exp_pdf)

        btn_exp_xlsx = QPushButton("📊 Exportar Excel")
        btn_exp_xlsx.setCursor(Qt.PointingHandCursor)
        btn_exp_xlsx.setToolTip("Exportar a Excel (.xlsx) los productos con stock actual menor o igual al mínimo")
        btn_exp_xlsx.clicked.connect(self._exportar_bajo_stock_excel)
        hdr.addWidget(btn_exp_xlsx)

        btn_ajuste = QPushButton("+ Nuevo Ajuste de Stock")
        btn_ajuste.setObjectName("btn_primary")
        btn_ajuste.setCursor(Qt.PointingHandCursor)
        btn_ajuste.clicked.connect(self._nuevo_ajuste)
        hdr.addWidget(btn_ajuste)

        btn_refresh = QPushButton("⟳ Actualizar")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self.actualizar)
        hdr.addWidget(btn_refresh)

        main_lay.addLayout(hdr)

        # ── 2. Tarjetas KPI (Métricas Clave) ─────────────────────────────────
        kpis_layout = QHBoxLayout()
        kpis_layout.setSpacing(10)

        self.kpi_costo = self._crear_kpi_card(
            "📦 INVERSIÓN (COSTO)", "Bs. 0.00", "0 productos", PALETTE["text_primary"], PALETTE["border"]
        )
        self.kpi_venta = self._crear_kpi_card(
            "🏷️ VALOR DE VENTA", "Bs. 0.00", "Valor en góndola", PALETTE["text_primary"], PALETTE["border"]
        )
        self.kpi_ganancia = self._crear_kpi_card(
            "📈 GANANCIA POTENCIAL", "+Bs. 0.00", "Margen: 0.0%", PALETTE["success"], "rgba(16, 185, 129, 0.4)"
        )
        self.kpi_ventas_real = self._crear_kpi_card(
            "💰 GANANCIA EN VENTAS", "+Bs. 0.00", "Ganancia real acumulada", PALETTE["accent"], "rgba(14, 165, 233, 0.4)"
        )
        self.kpi_alertas = self._crear_kpi_card(
            "⚠️ ALERTAS DE STOCK", "0 Críticos", "0 agotados · 0 bajos", PALETTE["warning"], "rgba(245, 158, 11, 0.4)"
        )

        kpis_layout.addWidget(self.kpi_costo)
        kpis_layout.addWidget(self.kpi_venta)
        kpis_layout.addWidget(self.kpi_ganancia)
        kpis_layout.addWidget(self.kpi_ventas_real)
        kpis_layout.addWidget(self.kpi_alertas)

        main_lay.addLayout(kpis_layout)

        # ── 3. Banner interactivo de Alerta de Stock ─────────────────────────
        self.alert_banner = QFrame()
        self.alert_banner.setObjectName("alert_banner")
        self.alert_banner.setStyleSheet(f"""
            QFrame#alert_banner {{
                background-color: rgba(245, 158, 11, 0.12);
                border: 1.5px solid {PALETTE['warning']};
                border-radius: 8px;
            }}
        """)
        alert_lay = QHBoxLayout(self.alert_banner)
        alert_lay.setContentsMargins(16, 8, 16, 8)
        alert_lay.setSpacing(14)

        self.lbl_alert_msg = QLabel("⚠ Existen productos que han alcanzado su stock mínimo o están agotados.")
        self.lbl_alert_msg.setStyleSheet(f"color: {PALETTE['warning']}; font-weight: bold; font-size: 13px; background: transparent; border: none;")
        alert_lay.addWidget(self.lbl_alert_msg)

        alert_lay.addStretch()

        btn_ver_alertas = QPushButton("Ver Productos Críticos →")
        btn_ver_alertas.setCursor(Qt.PointingHandCursor)
        btn_ver_alertas.setFixedHeight(30)
        btn_ver_alertas.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['warning']};
                color: #1c1917;
                border: none;
                border-radius: 6px;
                padding: 4px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #d97706;
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background-color: #b45309;
            }}
        """)
        btn_ver_alertas.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        alert_lay.addWidget(btn_ver_alertas)

        main_lay.addWidget(self.alert_banner)

        # ── 4. Pestañas de Contenido ─────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabs_inv")
        main_lay.addWidget(self.tabs, 1)

        self._build_tab_inventario_general()
        self._build_tab_alertas_stock()
        self._build_tab_ganancias_ventas()
        self._build_tab_historial_ajustes()

    def _crear_kpi_card(self, titulo: str, valor: str, subtitulo: str, color_valor: str, color_borde: str) -> QFrame:
        """Genera un componente visual tipo tarjeta métrica moderna."""
        card = QFrame()
        card.setObjectName("kpi_card")
        card.setStyleSheet(f"""
            QFrame#kpi_card {{
                background-color: {PALETTE['bg_card']};
                border: 1px solid {color_borde};
                border-radius: 9px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(3)

        lbl_t = QLabel(titulo)
        lbl_t.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        lay.addWidget(lbl_t)

        lbl_v = QLabel(valor)
        lbl_v.setObjectName("val_label")
        lbl_v.setStyleSheet(f"color: {color_valor}; font-size: 18px; font-weight: 800;")
        lay.addWidget(lbl_v)

        lbl_s = QLabel(subtitulo)
        lbl_s.setObjectName("sub_label")
        lbl_s.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px;")
        lay.addWidget(lbl_s)

        card.lbl_val = lbl_v
        card.lbl_sub = lbl_s
        return card

    # ─────────────────────────────────────────────────────────────────────────
    # PESTAÑA 1: Inventario Completo y Ganancias
    # ─────────────────────────────────────────────────────────────────────────
    def _build_tab_inventario_general(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 14, 12, 12)
        lay.setSpacing(10)

        # Barra de filtros
        filtros_row = QHBoxLayout()
        filtros_row.setSpacing(10)

        # Buscador
        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText("🔍 Buscar producto por código de barras o descripción...")
        self.input_buscar.setClearButtonEnabled(True)
        self.input_buscar.textChanged.connect(self._filtrar_tabla_inventario)
        filtros_row.addWidget(self.input_buscar, 2)

        # Filtro de categorías
        self.combo_cat = QComboBox()
        self.combo_cat.addItem("📂 Todas las Categorías", None)
        self.combo_cat.currentIndexChanged.connect(self._filtrar_tabla_inventario)
        filtros_row.addWidget(self.combo_cat, 1)

        # Filtro por estado de stock
        self.combo_estado = QComboBox()
        self.combo_estado.addItem("🏷️ Todos los Estados", "todos")
        self.combo_estado.addItem("🔴 Solo Agotados", "agotado")
        self.combo_estado.addItem("🟡 Solo Stock Bajo", "bajo")
        self.combo_estado.addItem("🟢 Solo Stock Óptimo", "normal")
        self.combo_estado.currentIndexChanged.connect(self._filtrar_tabla_inventario)
        filtros_row.addWidget(self.combo_estado, 1)

        lay.addLayout(filtros_row)

        # Tabla de inventario y ganancias
        self.tabla_inv = QTableWidget(0, 12)
        headers = [
            "Código", "Descripción del Producto", "Categoría",
            "Stock", "Mínimo", f"Costo ({CURRENCY})", f"Venta ({CURRENCY})",
            f"Gan. Unit.", "Margen %", f"Gan. Total",
            "Estado Stock", "Acción"
        ]
        self.tabla_inv.setHorizontalHeaderLabels(headers)

        header_inv = self.tabla_inv.horizontalHeader()
        header_inv.setSectionResizeMode(QHeaderView.Interactive)
        header_inv.setSectionResizeMode(1, QHeaderView.Stretch)
        header_inv.setFixedHeight(42)

        header_font = QFont("Segoe UI", 10, QFont.Bold)
        for col_idx in range(12):
            it = self.tabla_inv.horizontalHeaderItem(col_idx)
            if it:
                it.setFont(header_font)
                if col_idx in (0, 3, 4, 5, 6, 7, 8, 9, 10, 11):
                    it.setTextAlignment(Qt.AlignCenter)
                else:
                    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        anchos_inv = {
            0: 110,   # Código
            2: 120,   # Categoría
            3: 85,    # Stock
            4: 85,    # Mínimo
            5: 110,   # Costo (Bs)
            6: 110,   # Venta (Bs)
            7: 105,   # Gan. Unit.
            8: 90,    # Margen %
            9: 110,   # Gan. Total
            10: 135,  # Estado Stock
            11: 100,  # Acción
        }
        for col, ancho in anchos_inv.items():
            self.tabla_inv.setColumnWidth(col, ancho)

        self.tabla_inv.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_inv.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_inv.setAlternatingRowColors(True)
        self.tabla_inv.verticalHeader().setVisible(False)
        self.tabla_inv.verticalHeader().setDefaultSectionSize(44)

        lay.addWidget(self.tabla_inv, 1)

        # Pie con resumen de productos mostrados
        pie_lay = QHBoxLayout()
        self.lbl_conteo_inv = QLabel("Mostrando 0 productos")
        self.lbl_conteo_inv.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px;")
        pie_lay.addWidget(self.lbl_conteo_inv)
        pie_lay.addStretch()

        lbl_leyenda = QLabel("🟢 Óptimo  |  🟡 Stock Bajo  |  🔴 Agotado")
        lbl_leyenda.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px;")
        pie_lay.addWidget(lbl_leyenda)

        lay.addLayout(pie_lay)

        self.tabs.addTab(tab, "📊 Inventario y Ganancias")

    # ─────────────────────────────────────────────────────────────────────────
    # PESTAÑA 2: Alertas de Stock y Reposición
    # ─────────────────────────────────────────────────────────────────────────
    def _build_tab_alertas_stock(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 14, 12, 12)
        lay.setSpacing(12)

        # Banner informativo de reposición
        self.card_info_rep = QFrame()
        self.card_info_rep.setObjectName("card")
        rep_lay = QHBoxLayout(self.card_info_rep)
        rep_lay.setContentsMargins(14, 10, 14, 10)

        self.lbl_rep_info = QLabel("Cargando análisis de reposición...")
        self.lbl_rep_info.setStyleSheet(f"color: {PALETTE['text_primary']}; font-size: 13px; font-weight: bold;")
        rep_lay.addWidget(self.lbl_rep_info)

        rep_lay.addStretch()

        self.lbl_rep_costo = QLabel(f"Capital sugerido para reponer: {CURRENCY} 0.00")
        self.lbl_rep_costo.setStyleSheet(f"color: {PALETTE['warning']}; font-size: 14px; font-weight: bold;")
        rep_lay.addWidget(self.lbl_rep_costo)

        lay.addWidget(self.card_info_rep)

        # Tabla de alertas
        self.tabla_alertas = QTableWidget(0, 9)
        self.tabla_alertas.setHorizontalHeaderLabels([
            "Nivel", "Código", "Descripción", "Categoría",
            "Stock", "Mínimo", "Faltante", f"Costo Unit.", "Acción"
        ])
        header_alt = self.tabla_alertas.horizontalHeader()
        header_alt.setSectionResizeMode(QHeaderView.Interactive)
        header_alt.setSectionResizeMode(2, QHeaderView.Stretch)
        header_alt.setFixedHeight(42)

        header_font_alt = QFont("Segoe UI", 10, QFont.Bold)
        for col_idx in range(9):
            it = self.tabla_alertas.horizontalHeaderItem(col_idx)
            if it:
                it.setFont(header_font_alt)
                if col_idx in (0, 1, 4, 5, 6, 7, 8):
                    it.setTextAlignment(Qt.AlignCenter)
                else:
                    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        anchos_alt = {0: 105, 1: 110, 3: 120, 4: 90, 5: 90, 6: 95, 7: 110, 8: 135}
        for col, ancho in anchos_alt.items():
            self.tabla_alertas.setColumnWidth(col, ancho)

        self.tabla_alertas.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_alertas.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_alertas.setAlternatingRowColors(True)
        self.tabla_alertas.verticalHeader().setVisible(False)
        self.tabla_alertas.verticalHeader().setDefaultSectionSize(40)

        lay.addWidget(self.tabla_alertas, 1)

        self.tabs.addTab(tab, "⚠️ Alertas de Reposición")

    # ─────────────────────────────────────────────────────────────────────────
    # PESTAÑA 3: Ganancias Reales (Ventas Históricas)
    # ─────────────────────────────────────────────────────────────────────────
    def _build_tab_ganancias_ventas(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 14, 12, 12)
        lay.setSpacing(12)

        # Tarjetas de resumen de ventas
        resumen_box = QHBoxLayout()
        resumen_box.setSpacing(10)

        self.card_v_ingresos = self._crear_kpi_card(
            "💵 INGRESOS POR VENTAS", "Bs. 0.00", "Total vendido registrado", PALETTE["text_primary"], PALETTE["border"]
        )
        self.card_v_costo = self._crear_kpi_card(
            "📉 COSTO DE LO VENDIDO", "Bs. 0.00", "Costo de mercadería vendida", PALETTE["text_secondary"], PALETTE["border"]
        )
        self.card_v_ganancia = self._crear_kpi_card(
            "✨ GANANCIA NETA REAL", "+Bs. 0.00", "Utilidad bruta generada", PALETTE["success"], "rgba(16, 185, 129, 0.5)"
        )
        self.card_v_margen = self._crear_kpi_card(
            "📊 MARGEN REAL OBTENIDO", "0.0%", "Sobre ventas totales", PALETTE["accent"], PALETTE["border"]
        )

        resumen_box.addWidget(self.card_v_ingresos)
        resumen_box.addWidget(self.card_v_costo)
        resumen_box.addWidget(self.card_v_ganancia)
        resumen_box.addWidget(self.card_v_margen)
        lay.addLayout(resumen_box)

        # Título de la tabla de rendimiento
        lbl_top = QLabel("🏆 Productos con Mayor Ganancia Generada en Ventas")
        lbl_top.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {PALETTE['accent']}; margin-top: 6px;")
        lay.addWidget(lbl_top)

        # Tabla top productos vendidos
        self.tabla_ventas_prod = QTableWidget(0, 7)
        self.tabla_ventas_prod.setHorizontalHeaderLabels([
            "Código", "Producto", "Vendidos",
            f"Total Ventas ({CURRENCY})", f"Costo Total ({CURRENCY})",
            f"Ganancia Real ({CURRENCY})", "Margen %"
        ])
        header_vp = self.tabla_ventas_prod.horizontalHeader()
        header_vp.setSectionResizeMode(QHeaderView.Interactive)
        header_vp.setSectionResizeMode(1, QHeaderView.Stretch)
        header_vp.setFixedHeight(42)

        header_font_vp = QFont("Segoe UI", 10, QFont.Bold)
        for col_idx in range(7):
            it = self.tabla_ventas_prod.horizontalHeaderItem(col_idx)
            if it:
                it.setFont(header_font_vp)
                if col_idx in (0, 2, 3, 4, 5, 6):
                    it.setTextAlignment(Qt.AlignCenter)
                else:
                    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        anchos_vp = {0: 110, 2: 95, 3: 135, 4: 135, 5: 145, 6: 100}
        for col, ancho in anchos_vp.items():
            self.tabla_ventas_prod.setColumnWidth(col, ancho)

        self.tabla_ventas_prod.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_ventas_prod.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_ventas_prod.setAlternatingRowColors(True)
        self.tabla_ventas_prod.verticalHeader().setVisible(False)
        self.tabla_ventas_prod.verticalHeader().setDefaultSectionSize(38)

        lay.addWidget(self.tabla_ventas_prod, 1)

        self.tabs.addTab(tab, "💰 Ganancias en Ventas")

    # ─────────────────────────────────────────────────────────────────────────
    # PESTAÑA 4: Historial de Ajustes
    # ─────────────────────────────────────────────────────────────────────────
    def _build_tab_historial_ajustes(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 14, 12, 12)
        lay.setSpacing(10)

        # Tabla de historial
        self.tabla_ajustes = QTableWidget(0, 6)
        self.tabla_ajustes.setHorizontalHeaderLabels([
            "Fecha y Hora", "Producto", "Tipo Movimiento", "Cantidad", "Motivo", "Usuario Responsable"
        ])
        header_aj = self.tabla_ajustes.horizontalHeader()
        header_aj.setSectionResizeMode(QHeaderView.Interactive)
        header_aj.setSectionResizeMode(1, QHeaderView.Stretch)
        header_aj.setSectionResizeMode(4, QHeaderView.Stretch)
        self.tabla_ajustes.setColumnWidth(0, 155)
        self.tabla_ajustes.setColumnWidth(2, 160)
        self.tabla_ajustes.setColumnWidth(3, 100)
        self.tabla_ajustes.setColumnWidth(5, 180)
        header_aj.setFixedHeight(42)

        header_font = QFont("Segoe UI", 10, QFont.Bold)
        for col_idx in range(6):
            it = self.tabla_ajustes.horizontalHeaderItem(col_idx)
            if it:
                it.setFont(header_font)
                if col_idx in (0, 2, 3, 5):
                    it.setTextAlignment(Qt.AlignCenter)

        self.tabla_ajustes.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_ajustes.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_ajustes.setAlternatingRowColors(True)
        self.tabla_ajustes.verticalHeader().setVisible(False)
        self.tabla_ajustes.verticalHeader().setDefaultSectionSize(38)

        lay.addWidget(self.tabla_ajustes, 1)

        self.tabs.addTab(tab, "📋  Historial de Ajustes  ")

    # ─────────────────────────────────────────────────────────────────────────
    # CARGA Y ACTUALIZACIÓN DE DATOS
    # ─────────────────────────────────────────────────────────────────────────
    def actualizar(self):
        """Punto de entrada principal para recargar todos los datos y métricas."""
        try:
            self.session.expire_all()
        except Exception:
            pass
        try:
            self._cargar_categorias_combo()
            self._cargar_datos_principales()
            self._cargar_historial_ajustes()
            self._cargar_ganancias_ventas()
        except Exception as e:
            QMessageBox.critical(self, "Error al actualizar inventario", f"Ocurrió un detalle al cargar datos: {e}")

    def _cargar_categorias_combo(self):
        current_cat_id = self.combo_cat.currentData()
        self.combo_cat.blockSignals(True)
        self.combo_cat.clear()
        self.combo_cat.addItem("📂 Todas las Categorías", None)
        categorias = self.session.query(Categoria).order_by(Categoria.nombre).all()
        for c in categorias:
            self.combo_cat.addItem(c.nombre, c.id)

        # Restaurar selección si sigue existiendo
        if current_cat_id:
            idx = self.combo_cat.findData(current_cat_id)
            if idx >= 0:
                self.combo_cat.setCurrentIndex(idx)
        self.combo_cat.blockSignals(False)

    def _cargar_datos_principales(self):
        # Obtener todos los productos activos
        self._productos_cache = self.session.query(Producto).filter_by(activo=True).order_by(Producto.descripcion).all()

        total_costo = Decimal("0.00")
        total_venta = Decimal("0.00")
        agotados_count = 0
        bajos_count = 0

        for p in self._productos_cache:
            st = p.stock_actual
            pc = p.precio_compra_bs
            pv = p.precio_venta_bs

            # Acumuladores de valor
            if st > 0:
                total_costo += (st * pc)
                total_venta += (st * pv)

            if st <= 0:
                agotados_count += 1
            elif st <= p.stock_minimo:
                bajos_count += 1

        ganancia_potencial = total_venta - total_costo
        margen_proyectado = (ganancia_potencial / total_costo * 100) if total_costo > 0 else Decimal("0.0")
        total_alertas = agotados_count + bajos_count

        # Actualizar KPIs
        self.kpi_costo.lbl_val.setText(f"{CURRENCY} {total_costo:,.2f}")
        self.kpi_costo.lbl_sub.setText(f"{len(self._productos_cache)} productos registrados")

        self.kpi_venta.lbl_val.setText(f"{CURRENCY} {total_venta:,.2f}")
        self.kpi_venta.lbl_sub.setText("Valor estimado en góndola")

        self.kpi_ganancia.lbl_val.setText(f"+{CURRENCY} {ganancia_potencial:,.2f}")
        self.kpi_ganancia.lbl_sub.setText(f"Margen proyectado: +{margen_proyectado:.1f}%")

        self.kpi_alertas.lbl_val.setText(f"{total_alertas} Productos")
        self.kpi_alertas.lbl_sub.setText(f"{agotados_count} agotados · {bajos_count} con stock bajo")

        # Color dinámico de KPI de alertas
        if total_alertas > 0:
            self.kpi_alertas.lbl_val.setStyleSheet(f"color: {PALETTE['danger'] if agotados_count > 0 else PALETTE['warning']}; font-size: 18px; font-weight: 800;")
            self.alert_banner.setVisible(True)
            self.lbl_alert_msg.setText(
                f"⚠ Atención: Se encontraron {total_alertas} producto(s) críticos ({agotados_count} agotados y {bajos_count} bajo el mínimo)."
            )
            self.tabs.setTabText(1, f"⚠️ Alertas ({total_alertas})")
        else:
            self.kpi_alertas.lbl_val.setStyleSheet(f"color: {PALETTE['success']}; font-size: 18px; font-weight: 800;")
            self.alert_banner.setVisible(False)
            self.tabs.setTabText(1, "⚠️ Alertas (0)")

        # Llenar tablas
        self._filtrar_tabla_inventario()
        self._llenar_tabla_alertas()

    def _filtrar_tabla_inventario(self):
        """Aplica filtros de búsqueda por texto, categoría y estado."""
        query = self.input_buscar.text().strip().lower()
        cat_id = self.combo_cat.currentData()
        filtro_estado = self.combo_estado.currentData()

        filtrados: list[Producto] = []
        for p in self._productos_cache:
            # Filtro texto
            if query and not (query in p.descripcion.lower() or query in p.codigo_barras.lower()):
                continue

            # Filtro categoría
            if cat_id is not None and p.categoria_id != cat_id:
                continue

            # Filtro estado
            st = p.stock_actual
            if filtro_estado == "agotado" and st > 0:
                continue
            if filtro_estado == "bajo" and (st <= 0 or st > p.stock_minimo):
                continue
            if filtro_estado == "normal" and st <= p.stock_minimo:
                continue

            filtrados.append(p)

        self._renderizar_tabla_inventario(filtrados)

    def _renderizar_tabla_inventario(self, productos: list[Producto]):
        self.tabla_inv.setRowCount(len(productos))
        bold_font = QFont()
        bold_font.setBold(True)

        for i, p in enumerate(productos):
            st = p.stock_actual
            s_min = p.stock_minimo
            pc = p.precio_compra_bs
            pv = p.precio_venta_bs
            ganancia_u = pv - pc
            margen_u = (ganancia_u / pc * 100) if pc > 0 else Decimal("0.0")
            ganancia_tot = (st * ganancia_u) if st > 0 else Decimal("0.00")

            # 0. Código
            it_cod = QTableWidgetItem(p.codigo_barras)
            it_cod.setTextAlignment(Qt.AlignCenter)
            self.tabla_inv.setItem(i, 0, it_cod)

            # 1. Descripción
            it_desc = QTableWidgetItem(p.descripcion)
            it_desc.setFont(bold_font)
            self.tabla_inv.setItem(i, 1, it_desc)

            # 2. Categoría
            cat_nom = p.categoria.nombre if p.categoria else "-"
            it_cat = QTableWidgetItem(cat_nom)
            it_cat.setForeground(QBrush(QColor(PALETTE['text_secondary'])))
            self.tabla_inv.setItem(i, 2, it_cat)

            # 3. Stock Actual
            st_txt = str(int(st)) if st == int(st) else f"{st:.3f}".rstrip('0').rstrip('.')
            it_st = QTableWidgetItem(f"{st_txt} {p.unidad_medida}")
            it_st.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_st.setFont(bold_font)
            if st <= 0:
                it_st.setForeground(QBrush(QColor(PALETTE['danger'])))
            elif st <= s_min:
                it_st.setForeground(QBrush(QColor(PALETTE['warning'])))
            else:
                it_st.setForeground(QBrush(QColor(PALETTE['success'])))
            self.tabla_inv.setItem(i, 3, it_st)

            # 4. Stock Mínimo
            min_txt = str(int(s_min)) if s_min == int(s_min) else f"{s_min:.3f}".rstrip('0').rstrip('.')
            it_min = QTableWidgetItem(f"{min_txt} {p.unidad_medida}")
            it_min.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_min.setForeground(QBrush(QColor(PALETTE['text_muted'])))
            self.tabla_inv.setItem(i, 4, it_min)

            # 5. Costo
            it_pc = QTableWidgetItem(f"{pc:,.2f}")
            it_pc.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_inv.setItem(i, 5, it_pc)

            # 6. Venta
            it_pv = QTableWidgetItem(f"{pv:,.2f}")
            it_pv.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_inv.setItem(i, 6, it_pv)

            # 7. Ganancia Unitaria
            it_gu = QTableWidgetItem(f"+{ganancia_u:,.2f}")
            it_gu.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_gu.setFont(bold_font)
            it_gu.setForeground(QBrush(QColor(PALETTE['success'] if ganancia_u >= 0 else PALETTE['danger'])))
            self.tabla_inv.setItem(i, 7, it_gu)

            # 8. Margen %
            it_m = QTableWidgetItem(f"{margen_u:.1f}%")
            it_m.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_m.setForeground(QBrush(QColor(PALETTE['accent'])))
            self.tabla_inv.setItem(i, 8, it_m)

            # 9. Ganancia Total Stock
            it_gt = QTableWidgetItem(f"{ganancia_tot:,.2f}")
            it_gt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_gt.setFont(bold_font)
            it_gt.setForeground(QBrush(QColor(PALETTE['success'] if ganancia_tot > 0 else PALETTE['text_muted'])))
            self.tabla_inv.setItem(i, 9, it_gt)

            # 10. Estado (Badge)
            if st <= 0:
                badge_txt = "🔴 AGOTADO"
                color_b = QColor(PALETTE['danger'])
            elif st <= s_min:
                badge_txt = "🟡 STOCK BAJO"
                color_b = QColor(PALETTE['warning'])
            else:
                badge_txt = "🟢 ÓPTIMO"
                color_b = QColor(PALETTE['success'])

            it_est = QTableWidgetItem(badge_txt)
            it_est.setTextAlignment(Qt.AlignCenter)
            it_est.setFont(bold_font)
            it_est.setForeground(QBrush(color_b))
            self.tabla_inv.setItem(i, 10, it_est)

            # 11. Botón Acción encapsulado en contenedor centrado
            container_inv = QWidget()
            container_inv.setStyleSheet("background: transparent;")
            c_lay = QHBoxLayout(container_inv)
            c_lay.setContentsMargins(0, 0, 0, 0)
            c_lay.setAlignment(Qt.AlignCenter)

            btn_ajustar = QPushButton("Ajustar")
            btn_ajustar.setCursor(Qt.PointingHandCursor)
            if st <= s_min:
                btn_ajustar.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {PALETTE['warning']};
                        color: #1c1917;
                        border: none;
                        border-radius: 6px;
                        font-size: 12px;
                        font-weight: bold;
                        min-height: 28px;
                        max-height: 28px;
                        height: 28px;
                        min-width: 80px;
                        max-width: 80px;
                        width: 80px;
                        padding: 0px;
                        margin: 0px;
                        text-align: center;
                    }}
                    QPushButton:hover {{
                        background-color: #d97706;
                        color: white;
                    }}
                    QPushButton:pressed {{
                        background-color: #b45309;
                    }}
                """)
            else:
                btn_ajustar.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {PALETTE['bg_hover']};
                        color: {PALETTE['text_primary']};
                        border: 1px solid {PALETTE['border']};
                        border-radius: 6px;
                        font-size: 12px;
                        font-weight: 600;
                        min-height: 28px;
                        max-height: 28px;
                        height: 28px;
                        min-width: 80px;
                        max-width: 80px;
                        width: 80px;
                        padding: 0px;
                        margin: 0px;
                        text-align: center;
                    }}
                    QPushButton:hover {{
                        background-color: {PALETTE['accent']};
                        border-color: {PALETTE['accent']};
                        color: white;
                    }}
                    QPushButton:pressed {{
                        background-color: {PALETTE['accent_dark']};
                    }}
                """)
            btn_ajustar.clicked.connect(lambda checked, prod=p: self._nuevo_ajuste(prod))
            c_lay.addWidget(btn_ajustar)
            self.tabla_inv.setCellWidget(i, 11, container_inv)

        self.lbl_conteo_inv.setText(f"Mostrando {len(productos)} de {len(self._productos_cache)} productos")

    def _llenar_tabla_alertas(self):
        """Llena la pestaña de alertas con productos agotados o bajo el mínimo."""
        criticos = [p for p in self._productos_cache if p.stock_actual <= p.stock_minimo]
        # Ordenar: agotados primero, luego los más críticos
        criticos.sort(key=lambda x: (x.stock_actual > 0, x.stock_actual - x.stock_minimo))

        capital_sugerido = Decimal("0.00")
        for p in criticos:
            # Faltante para alcanzar el mínimo más un margen sugerido del 20%
            faltante = max(Decimal("0.0"), p.stock_minimo - p.stock_actual)
            capital_sugerido += (faltante * p.precio_compra_bs)

        self.lbl_rep_info.setText(f"Se encontraron {len(criticos)} producto(s) que requieren reposición urgente:")
        self.lbl_rep_costo.setText(f"Inversión necesaria para reposición: {CURRENCY} {capital_sugerido:,.2f}")

        self.tabla_alertas.setRowCount(len(criticos))
        bold_font = QFont()
        bold_font.setBold(True)

        for i, p in enumerate(criticos):
            st = p.stock_actual
            s_min = p.stock_minimo
            pc = p.precio_compra_bs
            faltante = max(Decimal("0.0"), s_min - st)

            # Nivel
            if st <= 0:
                it_nivel = QTableWidgetItem("🔴 AGOTADO")
                it_nivel.setForeground(QBrush(QColor(PALETTE['danger'])))
            else:
                it_nivel = QTableWidgetItem("🟡 BAJO")
                it_nivel.setForeground(QBrush(QColor(PALETTE['warning'])))
            it_nivel.setFont(bold_font)
            it_nivel.setTextAlignment(Qt.AlignCenter)
            self.tabla_alertas.setItem(i, 0, it_nivel)

            # Código
            it_cod = QTableWidgetItem(p.codigo_barras)
            it_cod.setTextAlignment(Qt.AlignCenter)
            self.tabla_alertas.setItem(i, 1, it_cod)

            # Descripción
            it_desc = QTableWidgetItem(p.descripcion)
            it_desc.setFont(bold_font)
            self.tabla_alertas.setItem(i, 2, it_desc)

            # Categoría
            it_cat = QTableWidgetItem(p.categoria.nombre if p.categoria else "-")
            it_cat.setForeground(QBrush(QColor(PALETTE['text_secondary'])))
            self.tabla_alertas.setItem(i, 3, it_cat)

            # Stock Actual
            st_txt = str(int(st)) if st == int(st) else f"{st:.3f}".rstrip('0').rstrip('.')
            it_st = QTableWidgetItem(f"{st_txt} {p.unidad_medida}")
            it_st.setFont(bold_font)
            it_st.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_st.setForeground(QBrush(QColor(PALETTE['danger'] if st <= 0 else PALETTE['warning'])))
            self.tabla_alertas.setItem(i, 4, it_st)

            # Stock Mínimo
            min_txt = str(int(s_min)) if s_min == int(s_min) else f"{s_min:.3f}".rstrip('0').rstrip('.')
            it_min = QTableWidgetItem(f"{min_txt} {p.unidad_medida}")
            it_min.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_alertas.setItem(i, 5, it_min)

            # Faltante sugerido
            f_txt = str(int(faltante)) if faltante == int(faltante) else f"{faltante:.3f}".rstrip('0').rstrip('.')
            it_fal = QTableWidgetItem(f"+{f_txt} {p.unidad_medida}")
            it_fal.setFont(bold_font)
            it_fal.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_fal.setForeground(QBrush(QColor(PALETTE['accent'])))
            self.tabla_alertas.setItem(i, 6, it_fal)

            # Costo unitario
            it_pc = QTableWidgetItem(f"{pc:,.2f}")
            it_pc.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_alertas.setItem(i, 7, it_pc)

            # Botón Ajustar encapsulado en contenedor centrado
            container_aj = QWidget()
            container_aj.setStyleSheet("background: transparent;")
            c_lay = QHBoxLayout(container_aj)
            c_lay.setContentsMargins(0, 0, 0, 0)
            c_lay.setAlignment(Qt.AlignCenter)

            btn_aj = QPushButton("Ajustar Stock")
            btn_aj.setCursor(Qt.PointingHandCursor)
            btn_aj.setStyleSheet(f"""
                QPushButton {{
                    background-color: {PALETTE['warning']};
                    color: #1c1917;
                    border: none;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: bold;
                    min-height: 28px;
                    max-height: 28px;
                    height: 28px;
                    min-width: 110px;
                    max-width: 110px;
                    width: 110px;
                    padding: 0px;
                    margin: 0px;
                    text-align: center;
                }}
                QPushButton:hover {{
                    background-color: #d97706;
                    color: white;
                }}
                QPushButton:pressed {{
                    background-color: #b45309;
                }}
            """)
            btn_aj.clicked.connect(lambda checked, prod=p: self._nuevo_ajuste(prod))
            c_lay.addWidget(btn_aj)
            self.tabla_alertas.setCellWidget(i, 8, container_aj)

    def _cargar_ganancias_ventas(self):
        """Calcula ingresos reales, costos de mercadería vendida y rentabilidad por producto."""
        ventas_completadas = self.session.query(Venta).filter(
            Venta.estado == Venta.ESTADO_COMPLETADA
        ).all()

        total_ingresos = Decimal("0.00")
        total_costo_vendido = Decimal("0.00")

        # Acumulador por producto: {prod_id: {'prod': prod, 'cant': D, 'ingresos': D, 'costo': D, 'ganancia': D}}
        por_prod = {}

        for v in ventas_completadas:
            for d in v.detalles:
                cant = d.cantidad
                ingreso = cant * d.precio_unitario_bs
                costo_u = d.producto.precio_compra_bs if d.producto else Decimal("0.00")
                costo_tot = cant * costo_u
                ganancia = ingreso - costo_tot

                total_ingresos += ingreso
                total_costo_vendido += costo_tot

                p_id = d.producto_id
                if p_id not in por_prod:
                    por_prod[p_id] = {
                        "producto": d.producto,
                        "codigo": d.producto.codigo_barras if d.producto else "-",
                        "descripcion": d.producto.descripcion if d.producto else f"Prod #{p_id}",
                        "cantidad": Decimal("0.00"),
                        "ingresos": Decimal("0.00"),
                        "costo": Decimal("0.00"),
                        "ganancia": Decimal("0.00"),
                    }
                por_prod[p_id]["cantidad"] += cant
                por_prod[p_id]["ingresos"] += ingreso
                por_prod[p_id]["costo"] += costo_tot
                por_prod[p_id]["ganancia"] += ganancia

        ganancia_real_neta = total_ingresos - total_costo_vendido
        margen_real = (ganancia_real_neta / total_ingresos * 100) if total_ingresos > 0 else Decimal("0.0")

        # Actualizar tarjeta KPI principal
        self.kpi_ventas_real.lbl_val.setText(f"+{CURRENCY} {ganancia_real_neta:,.2f}")
        self.kpi_ventas_real.lbl_sub.setText(f"En {len(ventas_completadas)} ventas completadas")

        # Actualizar tarjetas de pestaña 3
        self.card_v_ingresos.lbl_val.setText(f"{CURRENCY} {total_ingresos:,.2f}")
        self.card_v_costo.lbl_val.setText(f"{CURRENCY} {total_costo_vendido:,.2f}")
        self.card_v_ganancia.lbl_val.setText(f"+{CURRENCY} {ganancia_real_neta:,.2f}")
        self.card_v_margen.lbl_val.setText(f"{margen_real:.1f}%")

        # Ordenar productos por ganancia real descendente
        ranking = sorted(por_prod.values(), key=lambda x: x["ganancia"], reverse=True)

        self.tabla_ventas_prod.setRowCount(len(ranking))
        bold_font = QFont()
        bold_font.setBold(True)

        for i, item in enumerate(ranking):
            # 0. Código
            it_cod = QTableWidgetItem(item["codigo"])
            it_cod.setTextAlignment(Qt.AlignCenter)
            self.tabla_ventas_prod.setItem(i, 0, it_cod)

            # 1. Producto
            it_p = QTableWidgetItem(item["descripcion"])
            it_p.setFont(bold_font)
            self.tabla_ventas_prod.setItem(i, 1, it_p)

            # 2. Cantidad vendida
            cant = item["cantidad"]
            cant_txt = str(int(cant)) if cant == int(cant) else f"{cant:.3f}".rstrip('0').rstrip('.')
            it_c = QTableWidgetItem(cant_txt)
            it_c.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_ventas_prod.setItem(i, 2, it_c)

            # 3. Ingresos
            it_ing = QTableWidgetItem(f"{item['ingresos']:,.2f}")
            it_ing.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_ventas_prod.setItem(i, 3, it_ing)

            # 4. Costo
            it_cos = QTableWidgetItem(f"{item['costo']:,.2f}")
            it_cos.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_cos.setForeground(QBrush(QColor(PALETTE['text_secondary'])))
            self.tabla_ventas_prod.setItem(i, 4, it_cos)

            # 5. Ganancia Real
            g = item["ganancia"]
            it_g = QTableWidgetItem(f"+{g:,.2f}")
            it_g.setFont(bold_font)
            it_g.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_g.setForeground(QBrush(QColor(PALETTE['success'] if g >= 0 else PALETTE['danger'])))
            self.tabla_ventas_prod.setItem(i, 5, it_g)

            # 6. Margen %
            m = (g / item["ingresos"] * 100) if item["ingresos"] > 0 else Decimal("0.0")
            it_m = QTableWidgetItem(f"{m:.1f}%")
            it_m.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_m.setForeground(QBrush(QColor(PALETTE['accent'])))
            self.tabla_ventas_prod.setItem(i, 6, it_m)

    def _cargar_historial_ajustes(self):
        """Carga los últimos 250 ajustes de inventario registrados."""
        ajustes = self.session.query(AjusteInventario).order_by(
            AjusteInventario.fecha.desc()
        ).limit(250).all()

        self.tabla_ajustes.setRowCount(len(ajustes))
        bold_font = QFont()
        bold_font.setBold(True)

        for i, a in enumerate(ajustes):
            es_entrada = (a.tipo == AjusteInventario.TIPO_ENTRADA)
            cant_val = a.cantidad
            cant_txt = str(int(cant_val)) if cant_val == int(cant_val) else f"{cant_val:.3f}".rstrip('0').rstrip('.')

            # Fecha
            it_fecha = QTableWidgetItem(a.fecha.strftime("%d/%m/%Y %H:%M"))
            it_fecha.setTextAlignment(Qt.AlignCenter)
            self.tabla_ajustes.setItem(i, 0, it_fecha)

            # Producto
            prod_desc = a.producto.descripcion if a.producto else "(Producto eliminado)"
            it_prod = QTableWidgetItem(prod_desc)
            it_prod.setFont(bold_font)
            self.tabla_ajustes.setItem(i, 1, it_prod)

            # Tipo
            tipo_label = "➕ ENTRADA" if es_entrada else "➖ SALIDA"
            it_tipo = QTableWidgetItem(tipo_label)
            it_tipo.setFont(bold_font)
            it_tipo.setTextAlignment(Qt.AlignCenter)
            it_tipo.setForeground(QBrush(QColor(PALETTE['success'] if es_entrada else PALETTE['danger'])))
            self.tabla_ajustes.setItem(i, 2, it_tipo)

            # Cantidad
            it_cant = QTableWidgetItem(f"{'+' if es_entrada else '-'}{cant_txt}")
            it_cant.setFont(bold_font)
            it_cant.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_cant.setForeground(QBrush(QColor(PALETTE['success'] if es_entrada else PALETTE['danger'])))
            self.tabla_ajustes.setItem(i, 3, it_cant)

            # Motivo
            it_mot = QTableWidgetItem(a.motivo or "-")
            self.tabla_ajustes.setItem(i, 4, it_mot)

            # Responsable
            user_nom = a.usuario.username if a.usuario else "-"
            it_u = QTableWidgetItem(user_nom)
            it_u.setTextAlignment(Qt.AlignCenter)
            it_u.setForeground(QBrush(QColor(PALETTE['text_secondary'])))
            self.tabla_ajustes.setItem(i, 5, it_u)

    # ─────────────────────────────────────────────────────────────────────────
    # EXPORTACIÓN DE PRODUCTOS CON BAJO STOCK
    # ─────────────────────────────────────────────────────────────────────────
    def _productos_bajo_stock_ordenados(self) -> list[Producto]:
        """Obtiene los productos activos con stock actual <= mínimo, ordenados por criticidad."""
        productos = productos_con_stock_bajo(self.session)
        productos.sort(
            key=lambda p: (p.stock_actual > 0, p.stock_actual - p.stock_minimo, p.descripcion.lower())
        )
        return productos

    def _exportar_bajo_stock(self, formato: str) -> None:
        """Solicita la ruta y genera el reporte de bajo stock en PDF o Excel."""
        try:
            productos = self._productos_bajo_stock_ordenados()
        except Exception as e:
            QMessageBox.critical(
                self, "Error al consultar inventario",
                f"No se pudo obtener la lista de productos con bajo stock:\n{e}",
            )
            return

        if not productos:
            QMessageBox.information(
                self, "Sin productos con bajo stock",
                "No hay productos activos cuyo stock actual sea menor o igual al stock mínimo.\n"
                "No se generó ningún archivo.",
            )
            return

        if formato == "pdf":
            titulo_dialogo = "Exportar Productos con Bajo Stock a PDF"
            filtro = "Archivos PDF (*.pdf)"
            extension = ".pdf"
            funcion = exportar_productos_bajo_stock_pdf
        else:
            titulo_dialogo = "Exportar Productos con Bajo Stock a Excel"
            filtro = "Archivos Excel (*.xlsx)"
            extension = ".xlsx"
            funcion = exportar_productos_bajo_stock_excel

        nombre_defecto = f"productos_bajo_stock_{datetime.now().strftime('%Y%m%d_%H%M%S')}{extension}"
        path, _ = QFileDialog.getSaveFileName(self, titulo_dialogo, nombre_defecto, filtro)
        if not path:
            return

        if not path.lower().endswith(extension):
            path += extension

        try:
            funcion(productos, path)
        except PermissionError as e:
            QMessageBox.critical(
                self, "Error de permisos",
                f"No se pudo escribir el archivo en:\n{path}\n\n"
                f"Verifique que la carpeta tenga permisos de escritura y que el archivo no esté abierto.\n\n{e}",
            )
            return
        except Exception as e:
            QMessageBox.critical(
                self, "Error al exportar",
                f"No se pudo generar el reporte en {extension.upper()}:\n{e}",
            )
            return

        res = QMessageBox.question(
            self, "Exportación exitosa",
            f"Se exportaron {len(productos)} producto(s) con bajo stock en:\n{path}\n\n"
            "¿Desea abrir el archivo ahora?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if res == QMessageBox.Yes:
            try:
                os.startfile(path)
            except Exception as e:
                QMessageBox.warning(
                    self, "No se pudo abrir el archivo",
                    f"El archivo se generó correctamente, pero no se pudo abrir automáticamente:\n{e}",
                )

    def _exportar_bajo_stock_pdf(self) -> None:
        self._exportar_bajo_stock("pdf")

    def _exportar_bajo_stock_excel(self) -> None:
        self._exportar_bajo_stock("excel")

    def _nuevo_ajuste(self, producto=None):
        """Abre el diálogo para registrar un nuevo ajuste de inventario."""
        dlg = AjusteDialog(self.session, self.usuario, producto, parent=self)
        if dlg.exec():
            self.actualizar()
            self.datos_actualizados.emit("ajuste")

    def closeEvent(self, event):
        self.session.close()
        super().closeEvent(event)
