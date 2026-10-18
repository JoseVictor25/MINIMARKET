"""
ui/maestros_widget.py – Gestión de clientes, proveedores y categorías.
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QFormLayout, QMessageBox,
    QAbstractItemView, QTabWidget,
)

from database import SessionLocal
from models.cliente import Cliente
from models.proveedor import Proveedor
from models.categoria import Categoria


def _build_crud_tab(session, Modelo, campos: list, titulo: str):
    """
    Fábrica de pestañas CRUD genéricas para modelos simples.
    campos: [(attr_name, label_text), ...]
    """
    tab = QWidget()
    lay = QVBoxLayout(tab)
    lay.setContentsMargins(12, 12, 12, 12)
    lay.setSpacing(10)

    def cargar(filtro=""):
        query = session.query(Modelo)
        registros = query.all()
        if filtro:
            filtro_l = filtro.lower()
            registros = [r for r in registros
                         if any(filtro_l in str(getattr(r, f[0], "")).lower() for f in campos)]
        tabla.setRowCount(len(registros))
        for i, r in enumerate(registros):
            for j, (attr, _) in enumerate(campos):
                tabla.setItem(i, j, QTableWidgetItem(str(getattr(r, attr, ""))))
            tabla.item(i, 0).setData(Qt.UserRole, r.id)

    def nuevo():
        dlg = _SimpleDialog(session, Modelo, campos, titulo, parent=tab)
        if dlg.exec():
            cargar(buscar_input.text())

    def editar():
        row = tabla.currentRow()
        if row < 0:
            return
        rid = tabla.item(row, 0).data(Qt.UserRole)
        registro = session.get(Modelo, rid)
        if registro:
            dlg = _SimpleDialog(session, Modelo, campos, titulo, registro, parent=tab)
            if dlg.exec():
                cargar(buscar_input.text())

    def eliminar():
        row = tabla.currentRow()
        if row < 0:
            return
        rid = tabla.item(row, 0).data(Qt.UserRole)
        resp = QMessageBox.question(tab, "Eliminar", f"¿Eliminar este registro de {titulo}?")
        if resp == QMessageBox.Yes:
            r = session.get(Modelo, rid)
            if r:
                try:
                    session.delete(r)
                    session.commit()
                    cargar(buscar_input.text())
                except Exception as e:
                    session.rollback()
                    QMessageBox.critical(tab, "Error", f"No se puede eliminar: {e}")

    # Encabezado
    hdr = QHBoxLayout()
    lbl = QLabel(titulo)
    lbl.setObjectName("subtitle")
    hdr.addWidget(lbl)
    hdr.addStretch()

    buscar_input = QLineEdit()
    buscar_input.setPlaceholderText("🔍 Buscar...")
    buscar_input.setFixedWidth(220)
    buscar_input.textChanged.connect(cargar)
    hdr.addWidget(buscar_input)

    btn_nuevo = QPushButton("+ Nuevo")
    btn_nuevo.setObjectName("btn_primary")
    btn_nuevo.clicked.connect(nuevo)
    hdr.addWidget(btn_nuevo)
    lay.addLayout(hdr)

    # Tabla
    headers = [lbl for _, lbl in campos]
    tabla = QTableWidget(0, len(campos))
    tabla.setHorizontalHeaderLabels(headers)
    tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
    tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tabla.setAlternatingRowColors(True)
    tabla.verticalHeader().setVisible(False)
    tabla.doubleClicked.connect(editar)
    lay.addWidget(tabla, 1)

    btn_row = QHBoxLayout()
    btn_ed = QPushButton("✏ Editar")
    btn_ed.clicked.connect(editar)
    btn_row.addWidget(btn_ed)

    btn_del = QPushButton("🗑 Eliminar")
    btn_del.setObjectName("btn_danger")
    btn_del.clicked.connect(eliminar)
    btn_row.addWidget(btn_del)
    btn_row.addStretch()
    lay.addLayout(btn_row)

    cargar()
    return tab, cargar


class _SimpleDialog(QDialog):
    """Diálogo genérico para crear / editar registros de modelos simples."""

    def __init__(self, session, Modelo, campos, titulo, registro=None, parent=None):
        super().__init__(parent)
        self.session = session
        self.Modelo = Modelo
        self.campos = campos
        self.registro = registro
        self.setWindowTitle(f"{'Editar' if registro else 'Nuevo'} {titulo}")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        lay = QFormLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        self.inputs = {}
        for attr, label in self.campos:
            inp = QLineEdit()
            if self.registro:
                inp.setText(str(getattr(self.registro, attr, "") or ""))
            lay.addRow(label, inp)
            self.inputs[attr] = inp

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Guardar")
        btn_save.setObjectName("btn_primary")
        btn_save.clicked.connect(self._guardar)
        btn_row.addWidget(btn_save)

        lay.addRow("", btn_row)

    def _guardar(self):
        # El primer campo es obligatorio
        primer_attr = self.campos[0][0]
        if not self.inputs[primer_attr].text().strip():
            QMessageBox.warning(self, "Error", f"El campo '{self.campos[0][1]}' es obligatorio.")
            return

        if not self.registro:
            self.registro = self.Modelo()
            self.session.add(self.registro)

        for attr, _ in self.campos:
            val = self.inputs[attr].text().strip() or None
            setattr(self.registro, attr, val)

        try:
            self.session.commit()
            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "Error", f"No se pudo guardar: {e}")


class MaestrosWidget(QWidget):
    """Panel con pestañas para Clientes, Proveedores y Categorías."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = SessionLocal()
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)

        tabs = QTabWidget()
        lay.addWidget(tabs)

        # Clientes
        tab_cli, _ = _build_crud_tab(
            self.session, Cliente,
            [("nit", "NIT"), ("razon_social", "Razón Social"),
             ("telefono", "Teléfono"), ("direccion", "Dirección")],
            "Clientes"
        )
        tabs.addTab(tab_cli, "👤 Clientes")

        # Proveedores
        tab_prov, _ = _build_crud_tab(
            self.session, Proveedor,
            [("nit", "NIT"), ("razon_social", "Razón Social"),
             ("telefono", "Teléfono"), ("direccion", "Dirección")],
            "Proveedores"
        )
        tabs.addTab(tab_prov, "🏭 Proveedores")

        # Categorías
        tab_cat, _ = _build_crud_tab(
            self.session, Categoria,
            [("nombre", "Nombre"), ("descripcion", "Descripción")],
            "Categorías"
        )
        tabs.addTab(tab_cat, "🏷 Categorías")

    def closeEvent(self, event):
        self.session.close()
        super().closeEvent(event)
