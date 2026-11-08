"""Búsqueda de productos en el formulario de compras, sin base real."""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication

from ui.compras_widget import NuevaCompraDialog


class _Consulta:
    def __init__(self, productos):
        self.productos = productos

    def filter_by(self, **_):
        return self

    def order_by(self, *_):
        return self

    def all(self):
        return self.productos


class _Sesion:
    def __init__(self, productos):
        self.productos = productos

    def query(self, modelo):
        return _Consulta(self.productos if modelo.__name__ == "Producto" else [])

    def get(self, _modelo, producto_id):
        return next((p for p in self.productos if p.id == producto_id), None)


def test_compras_filtra_acentos_limita_resultados_y_enter_selecciona():
    app = QApplication.instance() or QApplication([])
    productos = [
        SimpleNamespace(id=i, codigo_barras=f"COD{i:04d}",
                        descripcion=f"Cafe molido {i}", precio_compra_bs=12.5)
        for i in range(1001)
    ]
    productos[501].descripcion = "Café especial"
    dialogo = NuevaCompraDialog(session=_Sesion(productos))
    dialogo._filtrar_productos("cafe")
    assert dialogo._modelo_busqueda.rowCount() == 20
    dialogo._filtrar_productos("especial")
    assert dialogo._modelo_busqueda.rowCount() == 1
    dialogo.combo_prod.setEditText("especial")
    dialogo._completador_producto.popup().setCurrentIndex(
        dialogo._modelo_busqueda.index(0, 0)
    )
    evento = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    assert dialogo.eventFilter(dialogo.combo_prod.lineEdit(), evento)
    assert dialogo.combo_prod.currentData() == productos[501].id
    assert dialogo.input_cant.text() == "1"
    assert dialogo.input_precio.text() == "12.50"
    dialogo.close()
    assert app is not None
