"""Geometría y contraste de la botonera, sin usar minimarket.db."""
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QPushButton
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
import models  # noqa: F401
from models.categoria import Categoria
from models.producto import Producto
from ui.styles import BUTTON_COLORS, BUTTON_METRICS, STYLESHEET, configurar_boton


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
