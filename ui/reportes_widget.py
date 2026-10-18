"""
ui/reportes_widget.py – Módulo interactivo de Reportes y Estadísticas de Ventas.
Incluye filtros de períodos, tarjetas KPI, desglose por métodos de pago,
ranking de productos más vendidos, desempeño de cajeros y exportación PDF/Excel.
"""
from __future__ import annotations

import os
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path

from PyQt5.QtCore import Qt, QDate
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QDateEdit, QFrame,
    QTabWidget, QMessageBox, QFileDialog, QAbstractItemView,
    QProgressBar, QScrollArea,
)
from PyQt5.QtGui import QFont, QColor

from database import SessionLocal, get_session
from models.usuario import Usuario
from config import CURRENCY, APP_NAME
from ui.styles import PALETTE, configurar_calendario_elegante
from services.reporte_service import (
    obtener_metricas_generales,
    obtener_ventas_cronologicas,
    obtener_top_productos,
    obtener_desglose_metodos_pago,
    obtener_rendimiento_cajeros,
    generar_reporte_pdf,
    exportar_ventas_csv,
)


class ReportesWidget(QWidget):
    """Panel analítico de estadísticas y reportes ejecutivos de ventas."""

    def __init__(self, usuario: Usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self._build_ui()
        # Período por defecto: Este Mes
        self._set_periodo_mes_actual()
        self.actualizar()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        # ── 1. Barra Superior y Filtros ───────────────────────────────────────
        top_bar = QHBoxLayout()
        lbl_tit = QLabel("REPORTES Y ESTADÍSTICAS DE VENTAS")
        lbl_tit.setFont(QFont("Segoe UI", 16, QFont.Bold))
        lbl_tit.setStyleSheet(f"color: {PALETTE['white']}; letter-spacing: 1px;")
        top_bar.addWidget(lbl_tit)
        top_bar.addStretch()

        self.btn_export_excel = QPushButton("📊 Exportar Excel")
        self.btn_export_excel.setFixedHeight(36)
        self.btn_export_excel.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['bg_hover']};
                color: {PALETTE['text_primary']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 8px;
                padding: 0 14px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {PALETTE['bg_card']};
                color: white;
            }}
        """)
        self.btn_export_excel.clicked.connect(self._exportar_excel)
        top_bar.addWidget(self.btn_export_excel)

        self.btn_pdf = QPushButton("📄 Informe PDF Oficial")
        self.btn_pdf.setFixedHeight(36)
        self.btn_pdf.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {PALETTE['accent_hover']}; }}
        """)
        self.btn_pdf.clicked.connect(self._generar_pdf)
        top_bar.addWidget(self.btn_pdf)

        root.addLayout(top_bar)

        # ── 2. Card de Filtros de Período y Cajero ────────────────────────────
        filtros_card = QFrame()
        filtros_card.setObjectName("filtros_card")
        filtros_card.setStyleSheet(f"""
            QFrame#filtros_card {{
                background: {PALETTE['bg_card']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 10px;
            }}
            QLabel {{
                color: {PALETTE['text_secondary']};
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            }}
            QDateEdit, QComboBox {{
                background: {PALETTE['bg_input']};
                color: {PALETTE['white']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 13px;
                min-height: 24px;
            }}
        """)
        f_lay = QHBoxLayout(filtros_card)
        f_lay.setContentsMargins(14, 10, 14, 10)
        f_lay.setSpacing(10)

        # Botones Rápidos de Período
        btn_estilo_rapido = f"""
            QPushButton {{
                background: {PALETTE['bg_surface']};
                color: {PALETTE['text_primary']};
                border: 1px solid {PALETTE['border']};
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {PALETTE['accent']};
                color: white;
            }}
        """

        btn_hoy = QPushButton("Hoy")
        btn_hoy.setStyleSheet(btn_estilo_rapido)
        btn_hoy.clicked.connect(self._set_periodo_hoy)
        f_lay.addWidget(btn_hoy)

        btn_ayer = QPushButton("Ayer")
        btn_ayer.setStyleSheet(btn_estilo_rapido)
        btn_ayer.clicked.connect(self._set_periodo_ayer)
        f_lay.addWidget(btn_ayer)

        btn_7d = QPushButton("7 Días")
        btn_7d.setStyleSheet(btn_estilo_rapido)
        btn_7d.clicked.connect(self._set_periodo_7d)
        f_lay.addWidget(btn_7d)

        btn_mes = QPushButton("Este Mes")
        btn_mes.setStyleSheet(btn_estilo_rapido)
        btn_mes.clicked.connect(self._set_periodo_mes_actual)
        f_lay.addWidget(btn_mes)

        f_lay.addSpacing(8)
        linea_v = QFrame()
        linea_v.setFrameShape(QFrame.VLine)
        linea_v.setStyleSheet(f"border-left: 1px solid {PALETTE['border']};")
        f_lay.addWidget(linea_v)
        f_lay.addSpacing(8)

        # Selectores de Fechas
        f_lay.addWidget(QLabel("Desde:"))
        self.date_desde = QDateEdit()
        self.date_desde.setCalendarPopup(True)
        self.date_desde.setDisplayFormat("dd/MM/yyyy")
        configurar_calendario_elegante(self.date_desde)
        f_lay.addWidget(self.date_desde)

        f_lay.addWidget(QLabel("Hasta:"))
        self.date_hasta = QDateEdit()
        self.date_hasta.setCalendarPopup(True)
        self.date_hasta.setDisplayFormat("dd/MM/yyyy")
        configurar_calendario_elegante(self.date_hasta)
        f_lay.addWidget(self.date_hasta)

        # Selector de Cajero
        f_lay.addWidget(QLabel("Cajero:"))
        self.combo_cajero = QComboBox()
        self.combo_cajero.addItem("👤 Todos los Cajeros", None)
        self._cargar_combo_cajeros()
        f_lay.addWidget(self.combo_cajero)

        btn_filtrar = QPushButton("🔎 Filtrar")
        btn_filtrar.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['accent_dark']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {PALETTE['accent']}; }}
        """)
        btn_filtrar.clicked.connect(self.actualizar)
        f_lay.addWidget(btn_filtrar)

        f_lay.addStretch()
        root.addWidget(filtros_card)

        # ── 3. Fila de Tarjetas KPI (Indicadores Clave) ────────────────────────
        kpis_grid = QGridLayout()
        kpis_grid.setSpacing(12)

        def crear_tarjeta_kpi(titulo: str, icon: str, color_val: str):
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {PALETTE['bg_card']};
                    border: 1.5px solid {PALETTE['border']};
                    border-radius: 12px;
                }}
            """)
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(16, 12, 16, 12)
            c_lay.setSpacing(4)

            t_lay = QHBoxLayout()
            lbl_ic = QLabel(icon)
            lbl_ic.setStyleSheet("font-size: 20px; background: transparent; border: none;")
            t_lay.addWidget(lbl_ic)

            lbl_t = QLabel(titulo)
            lbl_t.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px; font-weight: bold; letter-spacing: 0.5px; background: transparent; border: none;")
            t_lay.addWidget(lbl_t)
            t_lay.addStretch()
            c_lay.addLayout(t_lay)

            lbl_val = QLabel("0.00")
            lbl_val.setStyleSheet(f"font-size: 24px; font-weight: 900; color: {color_val}; background: transparent; border: none;")
            c_lay.addWidget(lbl_val)

            lbl_sub = QLabel("—")
            lbl_sub.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 12px; background: transparent; border: none;")
            c_lay.addWidget(lbl_sub)

            return card, lbl_val, lbl_sub

        self.kpi_ventas_card, self.lbl_kpi_ventas_val, self.lbl_kpi_ventas_sub = crear_tarjeta_kpi(
            "TOTAL VENTAS (FACTURADO)", "💰", PALETTE['success']
        )
        self.kpi_ganancia_card, self.lbl_kpi_ganancia_val, self.lbl_kpi_ganancia_sub = crear_tarjeta_kpi(
            "UTILIDAD / GANANCIA ESTIMADA", "📈", PALETTE['accent_hover']
        )
        self.kpi_ticket_card, self.lbl_kpi_ticket_val, self.lbl_kpi_ticket_sub = crear_tarjeta_kpi(
            "TICKET PROMEDIO", "🎫", PALETTE['white']
        )
        self.kpi_cant_card, self.lbl_kpi_cant_val, self.lbl_kpi_cant_sub = crear_tarjeta_kpi(
            "UNIDADES VENDIDAS", "📦", PALETTE['warning']
        )

        kpis_grid.addWidget(self.kpi_ventas_card, 0, 0)
        kpis_grid.addWidget(self.kpi_ganancia_card, 0, 1)
        kpis_grid.addWidget(self.kpi_ticket_card, 0, 2)
        kpis_grid.addWidget(self.kpi_cant_card, 0, 3)
        root.addLayout(kpis_grid)

        # ── 4. Pestañas de Análisis Detallado ──────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                background: {PALETTE['bg_surface']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 10px;
                top: -1px;
            }}
            QTabBar::tab {{
                background: {PALETTE['bg_base']};
                color: {PALETTE['text_secondary']};
                padding: 9px 18px;
                font-size: 13px;
                font-weight: 600;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border: 1px solid #1f293d;
                border-bottom: none;
                margin-right: 6px;
            }}
            QTabBar::tab:selected {{
                background: {PALETTE['bg_surface']};
                color: {PALETTE['accent_hover']};
                border: 1.5px solid {PALETTE['border']};
                border-bottom: 3px solid {PALETTE['accent']};
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background: {PALETTE['bg_card']};
                color: {PALETTE['white']};
                border-color: {PALETTE['border']};
            }}
        """)

        # Tab 1: Top Productos
        self.tab_top = QWidget()
        self._build_tab_top()
        self.tabs.addTab(self.tab_top, "🏆 Top Productos")

        # Tab 2: Métodos de Pago
        self.tab_pagos = QWidget()
        self._build_tab_pagos()
        self.tabs.addTab(self.tab_pagos, "💳 Formas de Pago")

        # Tab 3: Rendimiento por Cajero
        self.tab_cajeros = QWidget()
        self._build_tab_cajeros()
        self.tabs.addTab(self.tab_cajeros, "👥 Desempeño Cajeros")

        # Tab 4: Historial Diario
        self.tab_diario = QWidget()
        self._build_tab_diario()
        self.tabs.addTab(self.tab_diario, "📅 Tendencia Temporal")

        root.addWidget(self.tabs, 1)

    # ── Construcción de Pestañas ──────────────────────────────────────────────

    def _build_tab_top(self):
        lay = QVBoxLayout(self.tab_top)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        lbl = QLabel("Ranking de Productos con Mayor Facturación y Cantidad Despachada:")
        lbl.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px; font-weight: 600;")
        lay.addWidget(lbl)

        self.tabla_top = QTableWidget()
        self.tabla_top.setColumnCount(8)
        self.tabla_top.setHorizontalHeaderLabels([
            "#", "Código", "Descripción", "Categoría",
            "Cant. Vendida", f"Total Venta ({CURRENCY})", f"Ganancia ({CURRENCY})", "Margen %"
        ])
        self.tabla_top.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla_top.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabla_top.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_top.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_top.verticalHeader().setVisible(False)
        self.tabla_top.setAlternatingRowColors(True)
        lay.addWidget(self.tabla_top)

    def _build_tab_pagos(self):
        lay = QVBoxLayout(self.tab_pagos)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(14)

        lbl = QLabel("Distribución de Ingresos según el Medio de Pago del Cliente:")
        lbl.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px; font-weight: 600;")
        lay.addWidget(lbl)

        self.cards_pagos_container = QVBoxLayout()
        self.cards_pagos_container.setSpacing(12)
        lay.addLayout(self.cards_pagos_container)
        lay.addStretch()

    def _build_tab_cajeros(self):
        lay = QVBoxLayout(self.tab_cajeros)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        lbl = QLabel("Participación y Eficiencia en Ventas por Cajero:")
        lbl.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px; font-weight: 600;")
        lay.addWidget(lbl)

        self.tabla_cajeros = QTableWidget()
        self.tabla_cajeros.setColumnCount(6)
        self.tabla_cajeros.setHorizontalHeaderLabels([
            "Cajero", "Usuario", "Transacciones",
            f"Total Facturado ({CURRENCY})", f"Ticket Promedio ({CURRENCY})", "Participación %"
        ])
        self.tabla_cajeros.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla_cajeros.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla_cajeros.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_cajeros.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_cajeros.verticalHeader().setVisible(False)
        self.tabla_cajeros.setAlternatingRowColors(True)
        lay.addWidget(self.tabla_cajeros)

    def _build_tab_diario(self):
        lay = QVBoxLayout(self.tab_diario)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        lbl = QLabel("Movimiento Cronológico de Ventas en el Período Seleccionado:")
        lbl.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px; font-weight: 600;")
        lay.addWidget(lbl)

        self.tabla_diario = QTableWidget()
        self.tabla_diario.setColumnCount(4)
        self.tabla_diario.setHorizontalHeaderLabels([
            "Período / Fecha", "N° Ventas", f"Total Facturado ({CURRENCY})", f"Promedio por Venta ({CURRENCY})"
        ])
        self.tabla_diario.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla_diario.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla_diario.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_diario.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_diario.verticalHeader().setVisible(False)
        self.tabla_diario.setAlternatingRowColors(True)
        lay.addWidget(self.tabla_diario)

    # ── Métodos de Ayuda de Período ───────────────────────────────────────────

    def _set_periodo_hoy(self):
        hoy = QDate.currentDate()
        self.date_desde.setDate(hoy)
        self.date_hasta.setDate(hoy)
        self.actualizar()

    def _set_periodo_ayer(self):
        ayer = QDate.currentDate().addDays(-1)
        self.date_desde.setDate(ayer)
        self.date_hasta.setDate(ayer)
        self.actualizar()

    def _set_periodo_7d(self):
        hoy = QDate.currentDate()
        self.date_desde.setDate(hoy.addDays(-6))
        self.date_hasta.setDate(hoy)
        self.actualizar()

    def _set_periodo_mes_actual(self):
        hoy = QDate.currentDate()
        inicio_mes = QDate(hoy.year(), hoy.month(), 1)
        self.date_desde.setDate(inicio_mes)
        self.date_hasta.setDate(hoy)

    def _cargar_combo_cajeros(self):
        with get_session() as session:
            cajeros = session.query(Usuario).filter(Usuario.activo == True).order_by(Usuario.nombre_completo).all()
            for c in cajeros:
                self.combo_cajero.addItem(f"👤 {c.nombre_completo} ({c.username})", c.id)

    def _obtener_fechas_filtro(self) -> tuple[datetime, datetime]:
        d1 = self.date_desde.date()
        d2 = self.date_hasta.date()
        f_inicio = datetime(d1.year(), d1.month(), d1.day(), 0, 0, 0)
        f_fin = datetime(d2.year(), d2.month(), d2.day(), 23, 59, 59)
        return f_inicio, f_fin

    # ── Actualización de Datos y Renderizado ──────────────────────────────────

    def actualizar(self):
        """Recalcula métricas y llena todas las pestañas según los filtros activos."""
        f_inicio, f_fin = self._obtener_fechas_filtro()
        cajero_id = self.combo_cajero.currentData()

        with get_session() as session:
            # 1. KPIs Generales
            metricas = obtener_metricas_generales(session, f_inicio, f_fin, cajero_id)
            self.lbl_kpi_ventas_val.setText(f"{CURRENCY} {metricas['total_ventas']:.2f}")
            self.lbl_kpi_ventas_sub.setText(f"en {metricas['cant_transacciones']} ventas completadas")

            self.lbl_kpi_ganancia_val.setText(f"{CURRENCY} {metricas['ganancia_estimada']:.2f}")
            self.lbl_kpi_ganancia_sub.setText(f"Margen bruto: {metricas['margen_porcentaje']:.1f}%")

            self.lbl_kpi_ticket_val.setText(f"{CURRENCY} {metricas['ticket_promedio']:.2f}")
            self.lbl_kpi_ticket_sub.setText("Promedio por cliente")

            self.lbl_kpi_cant_val.setText(f"{metricas['unidades_vendidas']:.0f} unid.")
            self.lbl_kpi_cant_sub.setText("Productos despachados")

            # 2. Top Productos
            top_prods = obtener_top_productos(session, f_inicio, f_fin, limite=15, usuario_id=cajero_id)
            self.tabla_top.setRowCount(len(top_prods))
            for i, p in enumerate(top_prods):
                # Puesto con icono para el top 3
                num_txt = f"🥇 {i+1}" if i == 0 else (f"🥈 {i+1}" if i == 1 else (f"🥉 {i+1}" if i == 2 else str(i+1)))
                it_pos = QTableWidgetItem(num_txt)
                it_pos.setTextAlignment(Qt.AlignCenter)
                self.tabla_top.setItem(i, 0, it_pos)

                self.tabla_top.setItem(i, 1, QTableWidgetItem(p["codigo"]))
                self.tabla_top.setItem(i, 2, QTableWidgetItem(p["descripcion"]))
                self.tabla_top.setItem(i, 3, QTableWidgetItem(p["categoria"]))

                it_cant = QTableWidgetItem(f"{p['cantidad']:.0f}")
                it_cant.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla_top.setItem(i, 4, it_cant)

                it_tot = QTableWidgetItem(f"{p['total']:.2f}")
                it_tot.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla_top.setItem(i, 5, it_tot)

                it_gan = QTableWidgetItem(f"{p['ganancia']:.2f}")
                it_gan.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                it_gan.setForeground(QColor(PALETTE['success']))
                self.tabla_top.setItem(i, 6, it_gan)

                margen = (p["ganancia"] / p["total"] * 100) if p["total"] > 0 else Decimal("0.00")
                it_mg = QTableWidgetItem(f"{margen:.1f}%")
                it_mg.setTextAlignment(Qt.AlignCenter)
                self.tabla_top.setItem(i, 7, it_mg)

            # 3. Métodos de Pago
            pagos = obtener_desglose_metodos_pago(session, f_inicio, f_fin, cajero_id)
            self._render_cards_pagos(pagos)

            # 4. Rendimiento Cajeros
            cajeros = obtener_rendimiento_cajeros(session, f_inicio, f_fin)
            self.tabla_cajeros.setRowCount(len(cajeros))
            for i, c in enumerate(cajeros):
                self.tabla_cajeros.setItem(i, 0, QTableWidgetItem(c["nombre"]))
                self.tabla_cajeros.setItem(i, 1, QTableWidgetItem(c["username"]))

                it_tr = QTableWidgetItem(str(c["transacciones"]))
                it_tr.setTextAlignment(Qt.AlignCenter)
                self.tabla_cajeros.setItem(i, 2, it_tr)

                it_t = QTableWidgetItem(f"{c['total']:.2f}")
                it_t.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla_cajeros.setItem(i, 3, it_t)

                it_tp = QTableWidgetItem(f"{c['ticket_promedio']:.2f}")
                it_tp.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla_cajeros.setItem(i, 4, it_tp)

                it_pct = QTableWidgetItem(f"{c['porcentaje']:.1f}%")
                it_pct.setTextAlignment(Qt.AlignCenter)
                self.tabla_cajeros.setItem(i, 5, it_pct)

            # 5. Tendencia Diaria
            diario = obtener_ventas_cronologicas(session, f_inicio, f_fin, cajero_id)
            self.tabla_diario.setRowCount(len(diario))
            for i, d in enumerate(diario):
                it_d = QTableWidgetItem(d["label"])
                it_d.setTextAlignment(Qt.AlignCenter)
                self.tabla_diario.setItem(i, 0, it_d)

                it_cnt = QTableWidgetItem(str(d["cantidad"]))
                it_cnt.setTextAlignment(Qt.AlignCenter)
                self.tabla_diario.setItem(i, 1, it_cnt)

                it_val = QTableWidgetItem(f"{d['total']:.2f}")
                it_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla_diario.setItem(i, 2, it_val)

                prom = (d["total"] / d["cantidad"]) if d["cantidad"] > 0 else Decimal("0.00")
                it_p = QTableWidgetItem(f"{prom:.2f}")
                it_p.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla_diario.setItem(i, 3, it_p)

    def _render_cards_pagos(self, pagos: list[dict]):
        # Limpiar contenedor
        while self.cards_pagos_container.count():
            item = self.cards_pagos_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for p in pagos:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {PALETTE['bg_card']};
                    border: 1.5px solid {PALETTE['border']};
                    border-radius: 10px;
                    padding: 8px 14px;
                }}
            """)
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(12, 10, 12, 10)
            c_lay.setSpacing(6)

            h1 = QHBoxLayout()
            lbl_nom = QLabel(f"<b>{p['nombre']}</b>")
            lbl_nom.setStyleSheet(f"font-size: 14px; color: {PALETTE['white']}; border: none; background: transparent;")
            h1.addWidget(lbl_nom)
            h1.addStretch()

            lbl_m = QLabel(f"{CURRENCY} {p['monto']:.2f}  ({p['porcentaje']:.1f}%)")
            lbl_m.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {p['color']}; border: none; background: transparent;")
            h1.addWidget(lbl_m)
            c_lay.addLayout(h1)

            # Barra de progreso visual
            pbar = QProgressBar()
            pbar.setFixedHeight(8)
            pbar.setRange(0, 100)
            pbar.setValue(int(p["porcentaje"]))
            pbar.setTextVisible(False)
            pbar.setStyleSheet(f"""
                QProgressBar {{
                    background: {PALETTE['bg_input']};
                    border: none;
                    border-radius: 4px;
                }}
                QProgressBar::chunk {{
                    background: {p['color']};
                    border-radius: 4px;
                }}
            """)
            c_lay.addWidget(pbar)

            lbl_sub = QLabel(f"{p['transacciones']} cobros registrados mediante esta modalidad.")
            lbl_sub.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 12px; border: none; background: transparent;")
            c_lay.addWidget(lbl_sub)

            self.cards_pagos_container.addWidget(card)

    # ── Exportaciones (PDF y Excel) ───────────────────────────────────────────

    def _generar_pdf(self):
        f_inicio, f_fin = self._obtener_fechas_filtro()
        cajero_id = self.combo_cajero.currentData()

        try:
            with get_session() as session:
                pdf_ruta = generar_reporte_pdf(session, f_inicio, f_fin, cajero_id)

            if pdf_ruta and Path(pdf_ruta).exists():
                try:
                    os.startfile(str(pdf_ruta))
                except Exception:
                    QMessageBox.information(self, "Informe PDF", f"Informe generado exitosamente en:\n{pdf_ruta}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Generar PDF", f"No se pudo generar el informe:\n{e}")

    def _exportar_excel(self):
        f_inicio, f_fin = self._obtener_fechas_filtro()
        cajero_id = self.combo_cajero.currentData()

        ruta_sugerida = str(Path.home() / f"ventas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        destino, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Ventas a Excel (CSV)",
            ruta_sugerida,
            "Archivos CSV (*.csv)",
        )
        if not destino:
            return

        try:
            with get_session() as session:
                exportar_ventas_csv(session, f_inicio, f_fin, cajero_id, Path(destino))

            resp = QMessageBox.question(
                self,
                "Exportación Exitosa",
                f"✓ Archivo exportado exitosamente:\n{destino}\n\n¿Desea abrir el archivo en Excel ahora?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if resp == QMessageBox.Yes:
                try:
                    os.startfile(destino)
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"No se pudo exportar a Excel:\n{e}")
