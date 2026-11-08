"""Geometría y contraste de la botonera, sin usar minimarket.db."""
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import contextmanager
import importlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QHBoxLayout, QPushButton, QWidget
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
import models  # noqa: F401
from models.categoria import Categoria
from models.producto import Producto
from ui.styles import BUTTON_COLORS, BUTTON_METRICS, STYLESHEET, configurar_boton, igualar_fila


def _luminancia(color):
    valores = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    rgb = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
           for v in valores]
    return sum(a * b for a, b in zip(rgb, (.2126, .7152, .0722)))


def test_estados_de_boton_tienen_contraste_aa():
    for colores in BUTTON_COLORS.values():
        for fondo in colores:
            assert 1.05 / (_luminancia(fondo) + .05) >= 4.5
    assert (_luminancia("#f1f5f9") + .05) / (_luminancia("#374151") + .05) >= 4.5


def test_alturas_comunes_y_ancho_de_texto():
    app = QApplication.instance() or QApplication([])
    for tipo, (alto, _, _, _) in BUTTON_METRICS.items():
        boton = QPushButton("✕ Quitar producto")
        configurar_boton(boton, tipo)
        assert boton.height() == alto
        assert boton.minimumWidth() >= boton.fontMetrics().horizontalAdvance(boton.text())
    assert app is not None


def test_igualar_fila_con_tope_iguala_ancho_real():
    app = QApplication.instance() or QApplication([])
    contenedor = QWidget()
    fila = QHBoxLayout(contenedor)
    fila.addStretch()
    cancelar = QPushButton("Cancelar")
    guardar = QPushButton("Guardar")
    fila.addWidget(cancelar)
    fila.addWidget(guardar)
    igualar_fila(fila, cancelar, guardar, max_ancho=200)
    contenedor.resize(500, 90)
    contenedor.show()
    app.processEvents()
    assert cancelar.width() == guardar.width() <= 200
    assert cancelar.height() == guardar.height()
    assert cancelar.minimumWidth() <= cancelar.width()
    contenedor.close()


def test_inventario_cabe_en_ancho_logico_reducido(tmp_path):
    app = QApplication.instance() or QApplication([])
    estilo_anterior = app.styleSheet()
    app.setStyleSheet(STYLESHEET)
    engine = create_engine(f"sqlite:///{tmp_path / 'pruebas.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        categoria = Categoria(nombre="Pruebas", descripcion="Prueba visual")
        session.add(categoria)
        session.flush()
        producto = Producto(codigo_barras="COD001", descripcion="Producto de prueba",
                            unidad_medida="UN", categoria_id=categoria.id, activo=True)
        producto.stock_actual = Decimal("4")
        producto.stock_minimo = Decimal("2")
        producto.precio_compra_bs = Decimal("5")
        producto.precio_venta_bs = Decimal("10")
        session.add(producto)
        session.commit()
    from ui.inventario_widget import InventarioWidget
    with patch("ui.inventario_widget.SessionLocal", Session):
        inventario = InventarioWidget(SimpleNamespace())
    for ancho in (1000, 1280):
        inventario.resize(ancho, 700)
        inventario.show()
        app.processEvents()
        assert inventario.width() <= ancho
        assert inventario.tabla_inv.isColumnHidden(2)
        assert inventario.tabla_inv.isColumnHidden(9)
        header = inventario.tabla_inv.horizontalHeader()
        assert header.sectionViewportPosition(11) + header.sectionSize(11) <= inventario.tabla_inv.viewport().width()
        accion = inventario.tabla_inv.cellWidget(0, 11).findChild(QPushButton)
        assert accion.height() == BUTTON_METRICS["compact"][0]
        botones = [b for b in inventario.findChildren(QPushButton)
                   if b.isVisibleTo(inventario)]
        for boton in botones:
            esquina = boton.mapTo(inventario, boton.rect().topLeft())
            assert esquina.x() >= 0
            assert esquina.x() + boton.width() <= inventario.width()
    inventario.close()
    inventario.session.close()
    engine.dispose()
    app.setStyleSheet(estilo_anterior)


@pytest.mark.parametrize("modulo,clase", [
    ("productos_widget", "ProductosWidget"),
    ("compras_widget", "ComprasWidget"),
    ("ventas_widget", "VentasWidget"),
    ("reportes_widget", "ReportesWidget"),
    ("caja_widget", "CajaWidget"),
    ("usuarios_widget", "UsuariosWidget"),
    ("maestros_widget", "MaestrosWidget"),
    ("pos_widget", "POSWidget"),
])
def test_paneles_caben_en_1000_logicos(tmp_path, modulo, clase):
    app = QApplication.instance() or QApplication([])
    estilo_anterior = app.styleSheet()
    app.setStyleSheet(STYLESHEET)
    engine = create_engine(f"sqlite:///{tmp_path / 'pruebas.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    @contextmanager
    def sesion_temporal():
        with Session() as sesion:
            yield sesion

    m = importlib.import_module(f"ui.{modulo}")
    usuario = SimpleNamespace(id=1, username="prueba", nombre_completo="Usuario de prueba",
                              rol="admin", es_admin=lambda: True,
                              es_cajero=lambda: True)
    with patch.object(m, "SessionLocal", Session), \
         patch.object(m, "get_session", sesion_temporal, create=True):
        panel = getattr(m, clase)(usuario) if clase != "MaestrosWidget" else getattr(m, clase)()
        panel.resize(1000, 700)
        panel.show()
        app.processEvents()
        assert panel.width() <= 1000, f"{clase}: ancho mínimo {panel.width()}"
        for boton in panel.findChildren(QPushButton):
            if boton.isVisibleTo(panel):
                izquierda = boton.mapTo(panel, boton.rect().topLeft()).x()
                assert izquierda >= 0, f"{clase}: {boton.text()} fuera a la izquierda"
                assert izquierda + boton.width() <= panel.width(), (
                    f"{clase}: {boton.text()} fuera a la derecha"
                )
        panel.close()
        if hasattr(panel, "session"):
            panel.session.close()
    engine.dispose()
    app.setStyleSheet(estilo_anterior)
