"""Geometría y contraste de la botonera, sin usar minimarket.db."""
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import contextmanager
import importlib
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget
from PyQt5.QtGui import QFontMetrics
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


def test_productos_y_registrar_compra_no_estiran_botones(tmp_path):
    app = QApplication.instance() or QApplication([])
    engine = create_engine(f"sqlite:///{tmp_path / 'botones.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    usuario = SimpleNamespace(es_admin=lambda: True)
    from ui.productos_widget import ProductosWidget
    from ui.compras_widget import NuevaCompraDialog
    with patch("ui.productos_widget.SessionLocal", Session):
        productos = ProductosWidget(usuario)
    with Session() as sesion:
        compra = NuevaCompraDialog(usuario, sesion)
        for ventana, nombres, tope in (
            (productos, ("✏ Editar", "Estado"), 180),
            (compra, ("Cancelar", "Registrar"), 200),
        ):
            ventana.resize(1000, 700)
            ventana.show()
            app.processEvents()
            botones = {b.text(): b for b in ventana.findChildren(QPushButton)}
            primero, segundo = (botones[nombre] for nombre in nombres)
            assert primero.width() == segundo.width() <= tope
            assert primero.height() == segundo.height()
            for boton in (primero, segundo):
                assert boton.fontMetrics().horizontalAdvance(boton.text()) + 32 <= boton.width()
            ventana.close()
    productos.session.close()
    engine.dispose()


def test_fechas_de_reportes_permanecen_juntas(tmp_path):
    app = QApplication.instance() or QApplication([])
    engine = create_engine(f"sqlite:///{tmp_path / 'reportes.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    @contextmanager
    def sesion_temporal():
        with Session() as sesion:
            yield sesion

    from ui.reportes_widget import ReportesWidget
    usuario = SimpleNamespace(id=1, es_admin=lambda: True)
    with patch("ui.reportes_widget.SessionLocal", Session), \
         patch("ui.reportes_widget.get_session", sesion_temporal):
        panel = ReportesWidget(usuario)
        panel.resize(1000, 700)
        panel.show()
        app.processEvents()
        desde = panel.date_desde
        hasta = panel.date_hasta
        assert desde.width() == hasta.width() == 150
        distancia = hasta.mapTo(panel, hasta.rect().topLeft()).x() - (
            desde.mapTo(panel, desde.rect().topLeft()).x() + desde.width()
        )
        assert distancia < 100
        assert panel.combo_cajero.width() == 240
        panel.close()
    engine.dispose()


def test_cobro_exitoso_muestra_vuelto_sin_superponer_etiquetas():
    app = QApplication.instance() or QApplication([])
    from ui.pos_widget import CobroExitosoDialog
    dialogo = CobroExitosoDialog({
        "numero": 1, "total": Decimal("99"), "metodo": "efectivo",
        "monto_recibido": Decimal("101"), "vuelto": Decimal("2"),
    }, Path("ticket.pdf"))
    dialogo.show()
    app.processEvents()
    etiquetas = dialogo.findChildren(QLabel)
    titulo = next(e for e in etiquetas if e.text() == "VUELTO A ENTREGAR")
    monto = next(e for e in etiquetas if e.text() == "Bs 2.00")
    instruccion = next(e for e in etiquetas if e.text().startswith("Entregue el dinero"))
    metodo = next(e for e in etiquetas if "Recibido:" in e.text())
    def limites(etiqueta):
        y = etiqueta.mapTo(dialogo, etiqueta.rect().topLeft()).y()
        return y, y + etiqueta.height()
    assert limites(titulo)[1] <= limites(monto)[0]
    assert limites(monto)[1] <= limites(instruccion)[0]
    assert instruccion.height() >= instruccion.sizeHint().height()
    assert metodo.width() >= metodo.fontMetrics().horizontalAdvance("Efectivo")
    assert dialogo.btn_siguiente.isVisibleTo(dialogo)
    pantalla = dialogo.screen().availableGeometry()
    assert dialogo.width() <= pantalla.width() * .9 + 1
    assert dialogo.height() <= pantalla.height() * .9 + 1
    dialogo.close()


def test_quitar_compra_cabe_en_su_celda(tmp_path):
    from PyQt5.QtCore import QPoint
    from PyQt5.QtTest import QTest
    app = QApplication.instance() or QApplication([])
    engine = create_engine(f"sqlite:///{tmp_path / 'compra.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    from ui.compras_widget import NuevaCompraDialog
    with Session() as sesion:
        dialogo = NuevaCompraDialog(session=sesion)
        dialogo._items = [{
            "producto": SimpleNamespace(codigo_barras="001", descripcion="Producto"),
            "cantidad": Decimal("1"), "precio_unitario_bs": Decimal("2"),
        }]
        dialogo._refrescar_tabla()
        dialogo.show()
        app.processEvents()
        celda = dialogo.tabla.cellWidget(0, 5)
        boton = celda.findChild(QPushButton)
        margen = celda.layout().contentsMargins()
        assert dialogo.tabla.columnWidth(5) == 110
        assert dialogo.tabla.rowHeight(0) == 40
        assert (margen.left(), margen.top(), margen.right(), margen.bottom()) == (4, 4, 4, 4)
        assert boton.height() == BUTTON_METRICS["compact"][0] == 28
        assert boton.width() <= celda.width() - margen.left() - margen.right()
        assert boton.fontMetrics().horizontalAdvance(boton.text()) + boton.iconSize().width() + 10 <= boton.width()
        assert boton.grab().toImage().pixelColor(5, 14).name() == "#991b1b"
        QTest.mouseMove(boton, QPoint(5, 14))
        app.processEvents()
        assert boton.grab().toImage().pixelColor(5, 14).name() == "#7f1d1d"
        dialogo.close()
    engine.dispose()


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
    for ancho in (1000, 1280, 1536):
        inventario.resize(ancho, 700)
        inventario.show()
        app.processEvents()
        assert inventario.width() <= ancho
        assert inventario.tabla_inv.isColumnHidden(2) == (ancho < 1400)
        assert inventario.tabla_inv.isColumnHidden(9) == (ancho < 1400)
        header = inventario.tabla_inv.horizontalHeader()
        assert header.sectionViewportPosition(11) + header.sectionSize(11) <= inventario.tabla_inv.viewport().width()
        accion = inventario.tabla_inv.cellWidget(0, 11).findChild(QPushButton)
        assert accion.height() == BUTTON_METRICS["compact"][0]
        celda = inventario.tabla_inv.cellWidget(0, 11)
        esquina_accion = accion.mapTo(celda, accion.rect().topLeft())
        assert esquina_accion.x() >= 4
        assert esquina_accion.x() + accion.width() <= celda.width() - 4
        assert esquina_accion.y() >= 4
        assert inventario.tabla_inv.rowHeight(0) >= accion.height() + 8
        etiqueta_reporte, combo_reporte, pdf, excel = inventario._grupo_reporte
        assert etiqueta_reporte.mapTo(inventario, etiqueta_reporte.rect().topLeft()).x() <= 25
        assert combo_reporte.width() >= combo_reporte.fontMetrics().horizontalAdvance(
            combo_reporte.currentText()) + 40
        if ancho >= 1280:
            ajustar, actualizar = inventario._grupo_ajuste
            assert ajustar.y() == pdf.y() == actualizar.y()
        if ancho == 1536:
            margen = inventario.tabla_inv.horizontalHeaderItem(8)
            assert margen.text() == "Margen"
            assert header.sectionSize(8) >= QFontMetrics(margen.font()).horizontalAdvance(margen.text())
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
