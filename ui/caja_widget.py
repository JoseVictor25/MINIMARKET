"""
ui/caja_widget.py – Panel de Control y Arqueo de Caja.
Muestra el estado de la sesión actual y el historial completo de arqueos.
"""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView,
    QFrame, QDialog,
)
from PyQt5.QtGui import QFont

from database import SessionLocal, get_session
from models.caja import SesionCaja
from models.usuario import Usuario
from services.caja_service import (
    obtener_resumen_caja,
    generar_ticket_arqueo_pdf,
    cajas_abiertas,
    cajas_abiertas_usuario,
)
from ui.caja_dialog import AperturaCajaDialog, CierreCajaDialog
from config import CURRENCY
from ui.styles import PALETTE


class CajaWidget(QWidget):
    """Panel de gestión de sesiones de caja y arqueos."""

    datos_actualizados = pyqtSignal(str)

    def __init__(self, usuario: Usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self._build_ui()
        self.actualizar()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(14)

        # ── Título del Módulo ─────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        es_admin = self.usuario.es_admin()
        tit_texto = "AUDITORÍA Y CONTROL DE CAJAS" if es_admin else "MI CONTROL DE CAJA Y TURNO"
        lbl_tit = QLabel(tit_texto)
        lbl_tit.setFont(QFont("Segoe UI", 16, QFont.Bold))
        lbl_tit.setStyleSheet(f"color: {PALETTE['white']}; letter-spacing: 1px;")
        top_bar.addWidget(lbl_tit)
        top_bar.addStretch()

        btn_refrescar = QPushButton("🔄 Actualizar")
        btn_refrescar.setFixedHeight(34)
        btn_refrescar.setStyleSheet(f"""
            QPushButton {{
                background: {PALETTE['bg_hover']};
                color: {PALETTE['text_primary']};
                border: 1px solid {PALETTE['border']};
                border-radius: 6px;
                padding: 4px 14px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {PALETTE['bg_card']};
                color: white;
            }}
        """)
        btn_refrescar.clicked.connect(self.actualizar)
        top_bar.addWidget(btn_refrescar)
        lay.addLayout(top_bar)

        # ── Card de Estado de Caja Actual ─────────────────────────────────────
        self.card_actual = QFrame()
        self.card_actual.setObjectName("card_caja_actual")
        self.card_actual.setStyleSheet(f"""
            QFrame#card_caja_actual {{
                background-color: {PALETTE['bg_card']};
                border: 1.5px solid {PALETTE['border']};
                border-radius: 12px;
                padding: 6px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        self.lay_actual = QVBoxLayout(self.card_actual)
        self.lay_actual.setContentsMargins(16, 14, 16, 14)
        self.lay_actual.setSpacing(10)
        lay.addWidget(self.card_actual)

        # ── Sección Historial de Sesiones ─────────────────────────────────────
        subtit_hist = "Historial General de Arqueos (Todos los Cajeros)" if es_admin else "Mis Arqueos y Turnos Registrados"
        lbl_hist = QLabel(subtit_hist)
        lbl_hist.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl_hist.setStyleSheet(f"color: {PALETTE['text_secondary']};")
        lay.addWidget(lbl_hist)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(11)
        self.tabla.setHorizontalHeaderLabels([
            "# ID", "Cajero", "Turno", "Apertura", "Cierre",
            f"Base {CURRENCY}", f"Efec. Ventas", f"Total Ventas",
            f"Efec. Contado", "Diferencia", "Estado"
        ])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.doubleClicked.connect(self._ver_ticket_seleccionado)
        lay.addWidget(self.tabla, 1)

    def actualizar(self):
        """Actualiza el estado de la caja activa y el listado histórico."""
        self._render_caja_actual()
        self._cargar_historial()

    def actualizar_caja_actual(self):
        """Refresca solo la tarjeta de la caja propia, sin recalcular el historial."""
        self._render_caja_actual()

    def _render_caja_actual(self):
        # Limpiar completamente cualquier widget previo dentro de card_actual
        for child in self.card_actual.findChildren(QWidget):
            child.setParent(None)
            child.deleteLater()

        # Vaciar el layout recursivamente
        def _vaciar_layout(layout):
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
                l = item.layout()
                if l:
                    _vaciar_layout(l)

        _vaciar_layout(self.lay_actual)

        es_admin = self.usuario.es_admin()
        with get_session() as session:
            # La caja operativa es SIEMPRE la del usuario autenticado.
            # Las cajas ajenas solo se consultan para supervisión (admin).
            propias = cajas_abiertas_usuario(session, self.usuario.id)
            caja = propias[0] if propias else None
            ajenas = []
            if es_admin:
                ajenas = [c for c in cajas_abiertas(session) if c.usuario_id != self.usuario.id]

            if not caja:
                # Caja cerrada
                v_box = QVBoxLayout()
                v_box.setAlignment(Qt.AlignCenter)
                v_box.setSpacing(10)

                lbl_ico = QLabel("🔒")
                lbl_ico.setAlignment(Qt.AlignCenter)
                lbl_ico.setStyleSheet("font-size: 34px;")
                v_box.addWidget(lbl_ico)

                lbl_msg = QLabel("No tienes una caja abierta en este momento.")
                lbl_sub = QLabel(
                    "Abre tu propia caja para registrar movimientos y cobrar en el Punto de Venta."
                )

                lbl_msg.setAlignment(Qt.AlignCenter)
                lbl_msg.setFont(QFont("Segoe UI", 14, QFont.Bold))
                lbl_msg.setStyleSheet(f"color: {PALETTE['warning']};")
                v_box.addWidget(lbl_msg)

                lbl_sub.setAlignment(Qt.AlignCenter)
                lbl_sub.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px;")
                v_box.addWidget(lbl_sub)

                # Botón de Abrir Caja siempre disponible para cajeros, admins y usuarios con ambos roles
                btn_abrir = QPushButton("🔓  Abrir Caja de Turno")
                btn_abrir.setCursor(Qt.PointingHandCursor)
                btn_abrir.setFixedSize(210, 42)
                btn_abrir.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 #059669, stop:1 #047857);
                        color: white;
                        font-size: 14px;
                        font-weight: bold;
                        border: 1px solid #34d399;
                        border-radius: 8px;
                    }
                    QPushButton:hover {
                        background: #10b981;
                    }
                """)
                btn_abrir.clicked.connect(self._abrir_caja_dialog)

                btn_container = QHBoxLayout()
                btn_container.setAlignment(Qt.AlignCenter)
                btn_container.addWidget(btn_abrir)
                v_box.addLayout(btn_container)

                if ajenas:
                    ids_ajenas = ", ".join(f"#{c.id}" for c in ajenas)
                    lbl_sup = QLabel(
                        f"👁️ Supervisión: hay {len(ajenas)} caja(s) abierta(s) de otros usuarios ({ids_ajenas}). "
                        "No son operables desde esta sesión."
                    )
                    lbl_sup.setAlignment(Qt.AlignCenter)
                    lbl_sup.setWordWrap(True)
                    lbl_sup.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px;")
                    v_box.addWidget(lbl_sup)

                self.lay_actual.addLayout(v_box)
            else:
                # Caja abierta
                resumen = obtener_resumen_caja(session, caja.id)

                top_fila = QHBoxLayout()
                badge_abierta = QLabel(f"🟢 CAJA ABIERTA #{caja.id}")
                badge_abierta.setStyleSheet(f"""
                    background: rgba(34, 197, 94, 0.2);
                    color: {PALETTE['success']};
                    border: 1.5px solid {PALETTE['success']};
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-size: 13px;
                    font-weight: bold;
                """)
                top_fila.addWidget(badge_abierta)

                f_ap = caja.fecha_apertura.strftime("%d/%m/%Y %H:%M") if caja.fecha_apertura else "-"
                lbl_info = QLabel(
                    f"Cajero: <b>{resumen['usuario_nombre']}</b>  |  Turno: <b>{caja.turno}</b>  |  Apertura: <b>{f_ap}</b>"
                )
                lbl_info.setStyleSheet(f"color: {PALETTE['white']}; font-size: 14px;")
                top_fila.addWidget(lbl_info)
                top_fila.addStretch()

                btn_ticket = QPushButton("📄 Ver Arqueo Actual")
                btn_ticket.setFixedHeight(36)
                btn_ticket.setStyleSheet(f"""
                    QPushButton {{
                        background: {PALETTE['bg_hover']};
                        color: {PALETTE['text_primary']};
                        border: 1px solid {PALETTE['border']};
                        border-radius: 6px;
                        padding: 4px 12px;
                        font-size: 13px;
                    }}
                    QPushButton:hover {{ color: white; background: {PALETTE['bg_surface']}; }}
                """)
                btn_ticket.clicked.connect(lambda: self._imprimir_arqueo(caja.id))
                top_fila.addWidget(btn_ticket)

                btn_cerrar = QPushButton("🔒 Cerrar Caja (Arqueo)")
                btn_cerrar.setFixedHeight(36)
                btn_cerrar.setStyleSheet(f"""
                    QPushButton {{
                        background: {PALETTE['danger']};
                        color: white;
                        font-size: 13px;
                        font-weight: bold;
                        border: none;
                        border-radius: 6px;
                        padding: 4px 14px;
                    }}
                    QPushButton:hover {{ background: #dc2626; }}
                """)
                self.lay_actual.addLayout(top_fila)

                if len(propias) > 1:
                    ids_dup = ", ".join(f"#{c.id}" for c in propias)
                    lbl_dup = QLabel(
                        f"⚠️ Se detectaron {len(propias)} cajas abiertas para tu usuario ({ids_dup}). "
                        f"Se opera con la más reciente (#{caja.id}). "
                        "El sistema no las modifica automáticamente: revísalas y ciérralas una por una con su arqueo."
                    )
                    lbl_dup.setWordWrap(True)
                    lbl_dup.setStyleSheet(
                        f"color: {PALETTE['warning']}; font-size: 12px; "
                        f"background: rgba(245, 158, 11, 0.12); border: 1px solid {PALETTE['warning']}; "
                        "border-radius: 6px; padding: 6px 8px;"
                    )
                    self.lay_actual.addWidget(lbl_dup)

                    btn_dup = QPushButton("🧹 Revisar y cerrar cajas adicionales")
                    btn_dup.setCursor(Qt.PointingHandCursor)
                    btn_dup.setFixedHeight(32)
                    btn_dup.setStyleSheet(f"""
                        QPushButton {{
                            background: {PALETTE['bg_hover']};
                            color: {PALETTE['warning']};
                            border: 1px solid {PALETTE['warning']};
                            border-radius: 6px;
                            padding: 4px 12px;
                            font-size: 12px;
                            font-weight: bold;
                        }}
                        QPushButton:hover {{ color: white; background: {PALETTE['bg_surface']}; }}
                    """)
                    ids_adicionales = [c.id for c in propias[1:]]
                    btn_dup.clicked.connect(
                        lambda: self._cerrar_cajas_adicionales(ids_adicionales)
                    )
                    fila_dup = QHBoxLayout()
                    fila_dup.addStretch()
                    fila_dup.addWidget(btn_dup)
                    fila_dup.addStretch()
                    self.lay_actual.addLayout(fila_dup)

                if ajenas:
                    ids_ajenas = ", ".join(f"#{c.id}" for c in ajenas)
                    lbl_sup = QLabel(
                        f"👁️ Supervisión: {len(ajenas)} caja(s) abierta(s) de otros usuarios ({ids_ajenas}). "
                        "Solo consulta; no se pueden operar ni cerrar desde aquí."
                    )
                    lbl_sup.setWordWrap(True)
                    lbl_sup.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px;")
                    self.lay_actual.addWidget(lbl_sup)

                # Bloques con cifras destacadas
                chips_lay = QHBoxLayout()
                chips_lay.setSpacing(12)

                def chip_cifra(titulo: str, valor: str, color: str = PALETTE['white']):
                    f = QFrame()
                    f.setStyleSheet(f"""
                        background: {PALETTE['bg_surface']};
                        border: 1px solid {PALETTE['border']};
                        border-radius: 8px;
                        padding: 4px 8px;
                    """)
                    v = QVBoxLayout(f)
                    v.setContentsMargins(8, 6, 8, 6)
                    v.setSpacing(2)
                    lt = QLabel(titulo)
                    lt.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px; font-weight: 600;")
                    v.addWidget(lt)
                    lv = QLabel(valor)
                    lv.setStyleSheet(f"color: {color}; font-size: 17px; font-weight: bold;")
                    v.addWidget(lv)
                    return f

                chips_lay.addWidget(chip_cifra("Base Apertura", f"{CURRENCY} {resumen['base_inicial']:.2f}"))
                chips_lay.addWidget(chip_cifra("Ventas Efectivo", f"{CURRENCY} {resumen['ventas_efectivo']:.2f}"))
                chips_lay.addWidget(chip_cifra("Ventas QR", f"{CURRENCY} {resumen['ventas_qr']:.2f}"))
                chips_lay.addWidget(chip_cifra("Ventas Tarjeta", f"{CURRENCY} {resumen['ventas_tarjeta']:.2f}"))
                chips_lay.addWidget(chip_cifra("Total Facturado", f"{CURRENCY} {resumen['total_ventas']:.2f}", PALETTE['accent']))
                chips_lay.addWidget(chip_cifra("Efectivo Esperado", f"{CURRENCY} {resumen['total_efectivo_esperado']:.2f}", PALETTE['success']))

                self.lay_actual.addLayout(chips_lay)

    def _cargar_historial(self):
        with get_session() as session:
            query = session.query(SesionCaja)
            if not self.usuario.es_admin():
                query = query.filter(SesionCaja.usuario_id == self.usuario.id)
            sesiones = (
                query.order_by(SesionCaja.id.desc())
                .limit(50)
                .all()
            )

            self.tabla.setRowCount(len(sesiones))
            for i, s in enumerate(sesiones):
                cajero_nom = s.usuario.nombre_completo if s.usuario else "-"
                f_ap = s.fecha_apertura.strftime("%d/%m/%Y %H:%M") if s.fecha_apertura else "-"
                f_ci = s.fecha_cierre.strftime("%d/%m/%Y %H:%M") if s.fecha_cierre else "En curso"

                it_id = QTableWidgetItem(f"#{s.id}")
                it_id.setTextAlignment(Qt.AlignCenter)
                it_id.setData(Qt.UserRole, s.id)

                self.tabla.setItem(i, 0, it_id)
                self.tabla.setItem(i, 1, QTableWidgetItem(cajero_nom))
                self.tabla.setItem(i, 2, QTableWidgetItem(s.turno))
                self.tabla.setItem(i, 3, QTableWidgetItem(f_ap))
                self.tabla.setItem(i, 4, QTableWidgetItem(f_ci))

                it_base = QTableWidgetItem(f"{s.monto_inicial_bs:.2f}")
                it_base.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla.setItem(i, 5, it_base)

                # Calcular resumen rápido
                try:
                    res = obtener_resumen_caja(session, s.id)
                    v_efec = f"{res['ventas_efectivo']:.2f}"
                    v_tot = f"{res['total_ventas']:.2f}"
                except Exception:
                    v_efec = "-"
                    v_tot = "-"

                it_vef = QTableWidgetItem(v_efec)
                it_vef.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla.setItem(i, 6, it_vef)

                it_vtot = QTableWidgetItem(v_tot)
                it_vtot.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla.setItem(i, 7, it_vtot)

                m_fisico = f"{s.monto_final_efectivo_bs:.2f}" if s.monto_final_efectivo_bs is not None else "-"
                it_fis = QTableWidgetItem(m_fisico)
                it_fis.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla.setItem(i, 8, it_fis)

                dif_txt = "-"
                if s.diferencia_bs is not None:
                    if s.diferencia_bs == 0:
                        dif_txt = "Bs 0.00 (Cuadrada)"
                    elif s.diferencia_bs > 0:
                        dif_txt = f"+Bs {s.diferencia_bs:.2f} (Sobrante)"
                    else:
                        dif_txt = f"-Bs {abs(s.diferencia_bs):.2f} (Faltante)"

                it_dif = QTableWidgetItem(dif_txt)
                it_dif.setTextAlignment(Qt.AlignCenter)
                self.tabla.setItem(i, 9, it_dif)

                it_est = QTableWidgetItem(s.estado.upper())
                it_est.setTextAlignment(Qt.AlignCenter)
                if s.estado == "abierta":
                    it_est.setForeground(Qt.green)
                else:
                    it_est.setForeground(Qt.gray)
                self.tabla.setItem(i, 10, it_est)

    def _abrir_caja_dialog(self):
        dlg = AperturaCajaDialog(self.usuario, self)
        if dlg.exec() == QDialog.Accepted:
            self.actualizar()
            self.datos_actualizados.emit("caja")

    def _cerrar_caja_dialog(self, sesion_id: int):
        dlg = CierreCajaDialog(sesion_id, self.usuario, self)
        if dlg.exec() == QDialog.Accepted:
            self.actualizar()
            self.datos_actualizados.emit("caja")

    def _cerrar_cajas_adicionales(self, ids: list[int]):
        """Cierra, una por una y con arqueo explícito, cajas adicionales del mismo dueño."""
        cerrada_alguna = False
        for sesion_id in list(ids):
            dlg = CierreCajaDialog(sesion_id, self.usuario, self)
            if dlg.exec() != QDialog.Accepted:
                break
            cerrada_alguna = True
        if cerrada_alguna:
            self.actualizar()
            self.datos_actualizados.emit("caja")

    def _imprimir_arqueo(self, sesion_id: int):
        try:
            with get_session() as session:
                pdf_path = generar_ticket_arqueo_pdf(session, sesion_id)
            if pdf_path and Path(pdf_path).exists():
                try:
                    os.startfile(str(pdf_path))
                except Exception:
                    QMessageBox.information(self, "Ticket Generado", f"Archivo en:\n{pdf_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al generar arqueo:\n{e}")

    def _ver_ticket_seleccionado(self):
        row = self.tabla.currentRow()
        if row >= 0:
            it = self.tabla.item(row, 0)
            if it:
                sesion_id = it.data(Qt.UserRole)
                if sesion_id:
                    self._imprimir_arqueo(sesion_id)
