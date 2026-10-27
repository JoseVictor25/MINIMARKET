import os
import calendar
from datetime import datetime, date
from decimal import Decimal

from PyQt5.QtCore import Qt, QDate, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView, QSplitter,
    QFrame, QDialog, QScrollArea, QComboBox, QDateEdit, QFileDialog,
)

from database import SessionLocal
from models.venta import Venta
from models.usuario import Usuario
from services.venta_service import anular_venta
from services.ticket_service import generar_ticket_pdf
from services.export_service import exportar_ventas_excel, exportar_ventas_pdf
from config import CURRENCY, APP_NAME
from ui.styles import PALETTE, configurar_calendario_elegante
from ui.qr_dialog import VisualizadorImagenDialog


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


class DetalleVentaDialog(QDialog):
    """Muestra el detalle de una venta."""

    def __init__(self, venta: Venta, parent=None):
        super().__init__(parent)
        self.venta = venta
        self.setWindowTitle(f"Venta #{venta.numero_transaccion}")
        self.setMinimumSize(560, 460)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 20, 20, 20)

        # Info cabecera
        v = self.venta
        metodo_desc = "Mixto (QR + Efectivo)" if v.metodo_pago == "mixto" else v.metodo_pago.capitalize()
        qr_extra = ""
        if v.metodo_pago in ("QR", "qr") or v.qr_confirmado:
            qr_extra += "<br><b>Pago QR:</b> <span style='color:#22c55e; font-weight:bold;'>✓ Verificado y Confirmado</span>"
            if v.referencia_pago:
                qr_extra += f" &nbsp;|&nbsp; <b>Ref:</b> {v.referencia_pago}"

        obs_html = f"<br><b>Detalle pago:</b> {v.observacion}" if v.observacion else ""
        info = (
            f"<b>Transacción:</b> #{v.numero_transaccion} &nbsp;&nbsp; "
            f"<b>Fecha:</b> {v.fecha.strftime('%d/%m/%Y %H:%M')}<br>"
            f"<b>Estado:</b> <span style='color:{'#22c55e' if v.estado == 'completada' else '#ef4444'}; font-weight: bold;'>{v.estado.upper()}</span><br>"
            f"<b>Cajero:</b> {v.usuario.username if v.usuario else '-'}<br>"
            f"<b>Cliente:</b> {v.cliente.razon_social + ' (' + v.cliente.nit + ')' if v.cliente else 'Sin cliente'}<br>"
            f"<b>Método de pago:</b> {metodo_desc}{qr_extra}{obs_html}"
        )
        lbl_info = QLabel(info)
        lbl_info.setTextFormat(Qt.RichText)
        lbl_info.setStyleSheet("background: transparent;")
        lay.addWidget(lbl_info)

        # Botón para ver comprobante si existe
        if v.comprobante_pago:
            btn_comp = QPushButton("📎 Ver Comprobante / Captura de Pago Adjunto")
            btn_comp.setFixedHeight(34)
            btn_comp.setCursor(Qt.PointingHandCursor)
            btn_comp.setStyleSheet(f"""
                QPushButton {{
                    background: {PALETTE['bg_hover']};
                    color: {PALETTE['accent']};
                    border: 1px solid {PALETTE['border']};
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: {PALETTE['accent']};
                    color: #ffffff;
                }}
            """)
            btn_comp.clicked.connect(lambda: VisualizadorImagenDialog(
                v.comprobante_pago,
                titulo=f"Comprobante Venta #{v.numero_transaccion}",
                parent=self
            ).exec())
            lay.addWidget(btn_comp)

        # Tabla de detalle
        tabla = QTableWidget(len(v.detalles), 5)
        tabla.setHorizontalHeaderLabels(["Código", "Descripción", "Cant.", f"P. Venta {CURRENCY}", f"Subtotal {CURRENCY}"])
        tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tabla.verticalHeader().setVisible(False)
        tabla.setAlternatingRowColors(True)

        for i, d in enumerate(v.detalles):
            tabla.setItem(i, 0, QTableWidgetItem(d.producto.codigo_barras if d.producto else ""))
            tabla.setItem(i, 1, QTableWidgetItem(d.producto.descripcion if d.producto else ""))
            tabla.setItem(i, 2, QTableWidgetItem(f"{d.cantidad:.3f} {d.producto.unidad_medida if d.producto else ''}"))
            tabla.setItem(i, 3, QTableWidgetItem(f"{d.precio_unitario_bs:.2f}"))
            tabla.setItem(i, 4, QTableWidgetItem(f"{d.subtotal_bs:.2f}"))

        lay.addWidget(tabla, 1)

        # Total
        lbl_total = QLabel(f"TOTAL: {CURRENCY} {v.total_bs:.2f}")
        lbl_total.setObjectName("total_amount")
        lbl_total.setAlignment(Qt.AlignRight)
        lay.addWidget(lbl_total)

        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close)


class VentasWidget(QWidget):
    """Panel de historial de ventas con filtros por Día, Mes y Año, métricas y exportación a PDF/Excel."""

    datos_actualizados = pyqtSignal(str)

    def __init__(self, usuario: Usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.session = SessionLocal()
        self._ventas_filtradas: list[Venta] = []
        self._build_ui()
        self._cargar_ventas()

    def actualizar(self):
        """Refresca el historial conservando los filtros y la búsqueda actuales."""
        try:
            self.session.expire_all()
        except Exception:
            pass
        self._cargar_ventas()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(14)

        # ── 1. Barra de Título y Botones de Exportación ───────────────────────
        hdr = QHBoxLayout()
        lbl_tit = QLabel("HISTORIAL DE VENTAS")
        lbl_tit.setFont(QFont("Segoe UI", 15, QFont.Bold))
        lbl_tit.setStyleSheet("color: #ffffff; letter-spacing: 0.5px;")
        hdr.addWidget(lbl_tit)
        hdr.addStretch()

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
        hdr.addWidget(self.btn_export_excel)

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
        hdr.addWidget(self.btn_export_pdf)

        lay.addLayout(hdr)

        # ── 2. Tarjetas KPI Resumen ──────────────────────────────────────────
        kpis_lay = QHBoxLayout()
        kpis_lay.setSpacing(14)

        card1, self.lbl_kpi_total, self.lbl_kpi_total_sub = _crear_kpi_card("Total Recaudado (Válido)", f"{CURRENCY} 0.00", "#10b981", "Ventas completadas")
        card2, self.lbl_kpi_cant, self.lbl_kpi_cant_sub = _crear_kpi_card("Ventas Completadas", "0", "#38bdf8", "Transacciones exitosas")
        card3, self.lbl_kpi_anul, self.lbl_kpi_anul_sub = _crear_kpi_card("Ventas Anuladas", "0", "#ef4444", "Operaciones revertidas")

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

        # Selector de Fecha (Día / Hoy)
        self.date_picker = QDateEdit()
        self.date_picker.setFixedHeight(34)
        self.date_picker.setFixedWidth(130)
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setDisplayFormat("dd/MM/yyyy")
        configurar_calendario_elegante(self.date_picker)
        self.date_picker.dateChanged.connect(lambda: self._cargar_ventas())
        filter_lay.addWidget(self.date_picker)

        # Selector de Mes
        self.combo_mes = QComboBox()
        self.combo_mes.setFixedHeight(34)
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        self.combo_mes.addItems(meses)
        self.combo_mes.setCurrentIndex(datetime.now().month - 1)
        self.combo_mes.currentIndexChanged.connect(lambda: self._cargar_ventas())
        filter_lay.addWidget(self.combo_mes)

        # Selector de Año
        self.combo_anio = QComboBox()
        self.combo_anio.setFixedHeight(34)
        current_year = datetime.now().year
        for y in range(current_year - 5, current_year + 3):
            self.combo_anio.addItem(str(y))
        self.combo_anio.setCurrentText(str(current_year))
        self.combo_anio.currentIndexChanged.connect(lambda: self._cargar_ventas())
        filter_lay.addWidget(self.combo_anio)

        filter_lay.addStretch()

        # Búsqueda por texto en tiempo real
        self.input_buscar = QLineEdit()
        self.input_buscar.setFixedHeight(34)
        self.input_buscar.setFixedWidth(270)
        self.input_buscar.setPlaceholderText("🔍 Buscar N° trans., cliente, cajero...")
        self.input_buscar.textChanged.connect(lambda: self._cargar_ventas())
        filter_lay.addWidget(self.input_buscar)

        lay.addWidget(filter_frame)

        # ── 4. Tabla de Ventas ───────────────────────────────────────────────
        self.tabla = QTableWidget(0, 8)
        self.tabla.setHorizontalHeaderLabels([
            "N° Trans.", "Fecha y Hora", "Cajero", "Cliente", "NIT / CI",
            "Método", f"Total {CURRENCY}", "Estado"
        ])
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.tabla.setColumnWidth(0, 95)
        self.tabla.setColumnWidth(1, 140)
        self.tabla.setColumnWidth(2, 110)
        self.tabla.setColumnWidth(4, 105)
        self.tabla.setColumnWidth(5, 145)
        self.tabla.setColumnWidth(6, 115)
        self.tabla.setColumnWidth(7, 115)

        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.doubleClicked.connect(self._ver_detalle)
        lay.addWidget(self.tabla, 1)

        # ── 5. Botones de Acción Inferiores ──────────────────────────────────
        btn_row = QHBoxLayout()
        btn_ver = QPushButton("👁 Ver Detalle")
        btn_ver.setFixedHeight(34)
        btn_ver.setCursor(Qt.PointingHandCursor)
        btn_ver.setStyleSheet("""
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
        btn_ver.clicked.connect(self._ver_detalle)
        btn_row.addWidget(btn_ver)

        btn_ticket = QPushButton("🖨 Re-imprimir Ticket")
        btn_ticket.setFixedHeight(34)
        btn_ticket.setCursor(Qt.PointingHandCursor)
        btn_ticket.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 0 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)
        btn_ticket.clicked.connect(self._reimprimir)
        btn_row.addWidget(btn_ticket)

        btn_anular = QPushButton("✗ Anular Venta")
        btn_anular.setObjectName("btn_danger")
        btn_anular.setFixedHeight(34)
        btn_anular.setCursor(Qt.PointingHandCursor)
        btn_anular.setStyleSheet("""
            QPushButton#btn_danger {
                background-color: rgba(239, 68, 68, 0.15);
                color: #f87171;
                border: 1.5px solid #ef4444;
                border-radius: 6px;
                padding: 0 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton#btn_danger:hover {
                background-color: #ef4444;
                color: #ffffff;
            }
        """)
        btn_anular.clicked.connect(self._anular)
        btn_row.addWidget(btn_anular)

        if not self.usuario.es_admin():
            btn_anular.hide()

        btn_row.addStretch()
        self.lbl_conteo = QLabel("Mostrando 0 ventas")
        self.lbl_conteo.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 500;")
        btn_row.addWidget(self.lbl_conteo)

        lay.addLayout(btn_row)

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
            self._cargar_ventas()

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

    def _cargar_ventas(self):
        inicio, fin, periodo_str = self._obtener_fechas_filtro()
        query = self.session.query(Venta)

        if not self.usuario.es_admin():
            query = query.filter(Venta.usuario_id == self.usuario.id)

        if inicio and fin:
            query = query.filter(Venta.fecha >= inicio, Venta.fecha <= fin)

        ventas = query.order_by(Venta.fecha.desc()).all()

        # Filtrar por texto
        filtro_txt = self.input_buscar.text().strip().lower()
        if filtro_txt:
            ventas = [
                v for v in ventas
                if filtro_txt in str(v.numero_transaccion)
                or (v.usuario and filtro_txt in v.usuario.username.lower())
                or (v.cliente and filtro_txt in v.cliente.razon_social.lower())
                or (v.cliente and filtro_txt in (v.cliente.nit or "").lower())
                or filtro_txt in v.metodo_pago.lower()
                or filtro_txt in v.estado.lower()
                or filtro_txt in v.fecha.strftime("%d/%m/%Y")
            ]

        self._ventas_filtradas = ventas

        # Métricas KPI
        ventas_completadas = [v for v in ventas if v.estado == Venta.ESTADO_COMPLETADA]
        total_facturado = sum((v.total_bs for v in ventas_completadas), Decimal("0.00"))
        cant_completadas = len(ventas_completadas)
        cant_anuladas = len(ventas) - cant_completadas

        self.lbl_kpi_total.setText(f"{CURRENCY} {total_facturado:,.2f}")
        self.lbl_kpi_cant.setText(f"{cant_completadas} ventas")
        self.lbl_kpi_anul.setText(f"{cant_anuladas} anuladas")

        # Cargar Tabla
        self.tabla.setRowCount(len(ventas))
        for i, v in enumerate(ventas):
            if v.metodo_pago == "mixto":
                metodo_str = "🔄 Mixto (QR✓+Efec)" if v.qr_confirmado else "🔄 Mixto"
            elif v.metodo_pago in ("QR", "qr"):
                metodo_str = "📱 QR (✓)" if v.qr_confirmado else "📱 QR"
            else:
                metodo_str = v.metodo_pago.capitalize()

            cli_nom = v.cliente.razon_social if v.cliente else "Sin cliente"
            cli_nit = v.cliente.nit if v.cliente else "-"
            cajero_nom = v.usuario.username if v.usuario else "-"

            it_trans = QTableWidgetItem(f"#{v.numero_transaccion}")
            it_trans.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, 0, it_trans)

            it_fec = QTableWidgetItem(v.fecha.strftime("%d/%m/%Y %H:%M"))
            it_fec.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, 1, it_fec)

            it_caj = QTableWidgetItem(cajero_nom)
            it_caj.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, 2, it_caj)

            self.tabla.setItem(i, 3, QTableWidgetItem(cli_nom))

            it_nit = QTableWidgetItem(cli_nit)
            it_nit.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, 4, it_nit)

            it_met = QTableWidgetItem(metodo_str)
            it_met.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, 5, it_met)

            it_tot = QTableWidgetItem(f"{v.total_bs:,.2f}")
            it_tot.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            font_b = it_tot.font()
            font_b.setBold(True)
            it_tot.setFont(font_b)
            if v.estado == Venta.ESTADO_COMPLETADA:
                it_tot.setForeground(QColor("#10b981"))
            else:
                it_tot.setForeground(QColor("#64748b"))
            self.tabla.setItem(i, 6, it_tot)

            it_est = QTableWidgetItem(v.estado.upper())
            it_est.setTextAlignment(Qt.AlignCenter)
            font_est = it_est.font()
            font_est.setBold(True)
            it_est.setFont(font_est)
            if v.estado == Venta.ESTADO_COMPLETADA:
                it_est.setForeground(QColor("#10b981"))
            elif v.estado == Venta.ESTADO_ANULADA:
                it_est.setForeground(QColor("#ef4444"))
            self.tabla.setItem(i, 7, it_est)

            self.tabla.item(i, 0).setData(Qt.UserRole, v.id)

        self.lbl_conteo.setText(f"Mostrando {len(ventas)} venta(s) | {periodo_str}")

    def _get_venta_seleccionada(self) -> Venta | None:
        row = self.tabla.currentRow()
        if row < 0:
            return None
        venta_id = self.tabla.item(row, 0).data(Qt.UserRole)
        return self.session.get(Venta, venta_id)

    def _ver_detalle(self):
        v = self._get_venta_seleccionada()
        if not v:
            QMessageBox.information(self, "Seleccionar", "Haga clic en una venta para ver su detalle.")
            return
        dlg = DetalleVentaDialog(v, parent=self)
        dlg.exec()

    def _reimprimir(self):
        v = self._get_venta_seleccionada()
        if not v:
            QMessageBox.information(self, "Seleccionar", "Haga clic en una venta para re-imprimir su ticket.")
            return
        try:
            pdf = generar_ticket_pdf(v)
            os.startfile(str(pdf))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo generar el ticket:\n{e}")

    def _anular(self):
        v = self._get_venta_seleccionada()
        if not v:
            QMessageBox.information(self, "Seleccionar", "Haga clic en una venta para anularla.")
            return
        if v.estado == Venta.ESTADO_ANULADA:
            QMessageBox.information(self, "Info", "Esta venta ya está anulada.")
            return

        resp = QMessageBox.question(
            self, "Anular venta",
            f"¿Está seguro de anular la venta #{v.numero_transaccion} por {CURRENCY} {v.total_bs:.2f}?\n\n"
            "Se revertirá el stock de todos los productos incluidos en esta transacción.",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return

        try:
            anular_venta(self.session, v)
            self.session.commit()
            self.session.expire_all()
            self._cargar_ventas()
            self.datos_actualizados.emit("anulacion")
            QMessageBox.information(self, "Éxito", "La venta fue anulada y el stock fue revertido correctamente.")
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "Error", f"No se pudo anular la venta:\n{e}")

    def _exportar_excel(self):
        if not self._ventas_filtradas:
            QMessageBox.warning(self, "Sin Datos", "No hay ventas registradas en el período seleccionado para exportar.")
            return

        _, _, periodo_str = self._obtener_fechas_filtro()
        def_name = f"ventas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Ventas a Excel", def_name, "Archivos Excel (*.xlsx)")
        if not path:
            return

        try:
            exportar_ventas_excel(self._ventas_filtradas, path, periodo_str)
            res = QMessageBox.question(
                self, "Exportación Exitosa",
                f"El reporte de ventas en Excel se guardó correctamente en:\n{path}\n\n¿Desea abrir el archivo ahora?",
                QMessageBox.Yes | QMessageBox.No
            )
            if res == QMessageBox.Yes:
                os.startfile(path)
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"No se pudo generar el archivo Excel:\n{e}")

    def _exportar_pdf(self):
        if not self._ventas_filtradas:
            QMessageBox.warning(self, "Sin Datos", "No hay ventas registradas en el período seleccionado para exportar.")
            return

        _, _, periodo_str = self._obtener_fechas_filtro()
        def_name = f"ventas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Ventas a PDF", def_name, "Archivos PDF (*.pdf)")
        if not path:
            return

        try:
            exportar_ventas_pdf(self._ventas_filtradas, path, periodo_str)
            res = QMessageBox.question(
                self, "Exportación Exitosa",
                f"El reporte de ventas en PDF se generó exitosamente en:\n{path}\n\n¿Desea abrir el documento ahora?",
                QMessageBox.Yes | QMessageBox.No
            )
            if res == QMessageBox.Yes:
                os.startfile(path)
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"No se pudo generar el archivo PDF:\n{e}")

    def closeEvent(self, event):
        self.session.close()
        super().closeEvent(event)
