"""
tests/test_stock_insuficiente.py – Validación de stock y mensaje de error.

Cubre el DetachedInstanceError que ocurría al vender más unidades que el stock
disponible: la excepción conservaba el objeto ORM y la interfaz lo leía después
del rollback/cierre de la sesión.

Todas las pruebas usan una base SQLite temporal. No leen ni escriben
minimarket.db ni los respaldos.

Ejecutar:
    .\\venv\\Scripts\\python.exe tests\\test_stock_insuficiente.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
import models  # noqa: F401  (registra todas las tablas)

from models.categoria import Categoria
from models.producto import Producto
from models.usuario import Usuario
from models.venta import Venta

from services.caja_service import abrir_caja
from services.venta_service import StockInsuficienteError, registrar_venta

from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


class TempDBTestCase(unittest.TestCase):
    """Caso base con base SQLite aislada y sesiones de corta duración."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.engine = create_engine(
            f"sqlite:///{self.tmp_path / 'pruebas.db'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        self.session = self.Session()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.tmp.cleanup()

    def crear_usuario(self, username="cajero_stock") -> Usuario:
        u = Usuario(
            username=username,
            nombre_completo="Cajero Stock",
            rol="admin,cajero",
            activo=True,
        )
        u.set_password("Clave123")
        self.session.add(u)
        self.session.flush()
        return u

    def crear_producto(self, categoria, codigo, descripcion, stock,
                       minimo="1", precio_venta="10.00") -> Producto:
        p = Producto(
            codigo_barras=codigo,
            descripcion=descripcion,
            unidad_medida="UN",
            categoria_id=categoria.id,
            activo=True,
        )
        p.stock_actual = Decimal(str(stock))
        p.stock_minimo = Decimal(str(minimo))
        p.precio_compra_bs = Decimal("5.00")
        p.precio_venta_bs = Decimal(str(precio_venta))
        self.session.add(p)
        self.session.flush()
        return p

    def abrir_caja(self, usuario) -> int:
        caja = abrir_caja(self.session, usuario.id, turno="Mañana")
        self.session.commit()
        return caja.id

    @contextmanager
    def fake_get_session(self):
        """Equivalente a database.get_session(), sobre la base temporal."""
        s = self.Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()


class StockServiceTest(TempDBTestCase):

    def setUp(self):
        super().setUp()
        self.cat = Categoria(nombre="Limpieza", descripcion="Pruebas")
        self.session.add(self.cat)
        self.session.flush()
        self.user = self.crear_usuario()
        self.session.commit()
        self.caja_id = self.abrir_caja(self.user)

    def _vender_en_sesion_nueva(self, producto_id, cantidad):
        """Venta real desde una sesión nueva, igual que hace el POS."""
        with self.fake_get_session() as s:
            u = s.get(Usuario, self.user.id)
            p = s.get(Producto, producto_id)
            return registrar_venta(
                s,
                u,
                [{"producto": p, "cantidad": Decimal(str(cantidad))}],
                metodo_pago="efectivo",
                sesion_caja_id=self.caja_id,
            )

    def _stock(self, producto_id):
        self.session.expire_all()
        return self.session.get(Producto, producto_id).stock_actual

    def _ventas(self):
        self.session.expire_all()
        return self.session.query(Venta).count()

    def _crear_lavandina(self, stock=9):
        p = self.crear_producto(self.cat, f"LAV{stock}", "Lavandina", stock)
        self.session.commit()
        return p

    # ── Casos solicitados ────────────────────────────────────────────────────

    def test_stock_9_venta_10_rechazada_con_datos_primitivos(self):
        prod = self._crear_lavandina(9)

        with self.assertRaises(StockInsuficienteError) as ctx:
            self._vender_en_sesion_nueva(prod.id, 10)

        e = ctx.exception
        # La interfaz puede leer estos valores sin tocar el ORM desconectado.
        self.assertEqual(e.descripcion, "Lavandina")
        self.assertEqual(e.producto_id, prod.id)
        self.assertEqual(e.disponible, Decimal("9"))
        self.assertEqual(e.requerido, Decimal("10"))
        self.assertIn("Lavandina", str(e))
        self.assertFalse(hasattr(e, "producto"), "No debe exponer el objeto ORM")

        self.assertEqual(self._ventas(), 0)
        self.assertEqual(self._stock(prod.id), Decimal("9"))

    def test_stock_9_venta_9_permitida(self):
        prod = self._crear_lavandina(9)
        venta = self._vender_en_sesion_nueva(prod.id, 9)

        self.assertIsNotNone(venta.id)
        self.assertEqual(self._ventas(), 1)
        self.assertEqual(self._stock(prod.id), Decimal("0"))

    def test_stock_9_venta_1_permitida(self):
        prod = self._crear_lavandina(9)
        self._vender_en_sesion_nueva(prod.id, 1)

        self.assertEqual(self._ventas(), 1)
        self.assertEqual(self._stock(prod.id), Decimal("8"))

    def test_stock_0_venta_1_rechazada(self):
        prod = self._crear_lavandina(0)

        with self.assertRaises(StockInsuficienteError) as ctx:
            self._vender_en_sesion_nueva(prod.id, 1)

        self.assertEqual(ctx.exception.disponible, Decimal("0"))
        self.assertEqual(ctx.exception.requerido, Decimal("1"))
        self.assertEqual(self._ventas(), 0)
        self.assertEqual(self._stock(prod.id), Decimal("0"))

    def test_varios_articulos_uno_sin_stock_revierte_todo(self):
        p1 = self.crear_producto(self.cat, "OK1", "Arroz", 5)
        p2 = self.crear_producto(self.cat, "SIN1", "Aceite", 0)
        self.session.commit()

        with self.assertRaises(StockInsuficienteError) as ctx:
            with self.fake_get_session() as s:
                u = s.get(Usuario, self.user.id)
                items = [
                    {"producto": s.get(Producto, p1.id), "cantidad": Decimal("2")},
                    {"producto": s.get(Producto, p2.id), "cantidad": Decimal("1")},
                ]
                registrar_venta(
                    s, u, items, metodo_pago="efectivo",
                    sesion_caja_id=self.caja_id,
                )

        self.assertEqual(ctx.exception.descripcion, "Aceite")
        self.assertEqual(self._ventas(), 0)
        self.assertEqual(self._stock(p1.id), Decimal("5"))
        self.assertEqual(self._stock(p2.id), Decimal("0"))

    def test_error_sobrevive_al_rollback_y_cierre_de_sesion(self):
        """Regresión directa del DetachedInstanceError."""
        prod = self._crear_lavandina(9)

        with self.assertRaises(StockInsuficienteError) as ctx:
            with self.fake_get_session() as s:
                u = s.get(Usuario, self.user.id)
                p = s.get(Producto, prod.id)
                registrar_venta(
                    s, u,
                    [{"producto": p, "cantidad": Decimal("10")}],
                    metodo_pago="efectivo",
                    sesion_caja_id=self.caja_id,
                )

        e = ctx.exception
        # La sesión ya hizo rollback y close: solo se usan primitivas.
        mensaje = f"{e.descripcion}|{e.producto_id}|{e.disponible}|{e.requerido}"
        self.assertEqual(mensaje, f"Lavandina|{prod.id}|9|10")


class CobrarDialogStockTest(TempDBTestCase):

    def setUp(self):
        super().setUp()
        self.cat = Categoria(nombre="Limpieza", descripcion="Pruebas")
        self.session.add(self.cat)
        self.session.flush()
        self.user = self.crear_usuario()
        self.prod = self.crear_producto(self.cat, "LAV-9", "Lavandina", 9)
        self.session.commit()
        self.caja_id = self.abrir_caja(self.user)

        from ui.pos_widget import CobrarDialog

        self.dlg = CobrarDialog(
            total=Decimal("100.00"),
            session=self.session,
            items=[{"producto": self.prod, "cantidad": Decimal("10")}],
            usuario=self.user,
            cliente=None,
            sesion_caja_id=self.caja_id,
        )
        self.dlg.metodo_pago = "efectivo"
        self.dlg.monto_recibido = Decimal("100.00")
        self.dlg.vuelto = Decimal("0.00")

    def tearDown(self):
        self.dlg.close()
        super().tearDown()

    def _ventas(self):
        return self.session.query(Venta).count()

    def _stock(self):
        self.session.expire_all()
        return self.session.get(Producto, self.prod.id).stock_actual

    def test_mensaje_en_espanol_sin_detached_instance_error(self):
        with patch("ui.pos_widget.get_session", self.fake_get_session), \
             patch("ui.pos_widget.QMessageBox.warning") as aviso:
            self.dlg._confirmar()  # No debe propagar DetachedInstanceError

        aviso.assert_called_once()
        titulo, mensaje = aviso.call_args[0][1], aviso.call_args[0][2]
        self.assertEqual(titulo, "Stock insuficiente")
        self.assertIn("Lavandina", mensaje)
        self.assertIn("Stock disponible: 9", mensaje)
        self.assertIn("Cantidad solicitada: 10", mensaje)

        self.assertFalse(self.dlg.venta_confirmada)
        self.assertFalse(self.dlg._confirmando)
        self.assertTrue(self.dlg.btn_confirmar.isEnabled())
        self.assertEqual(self._ventas(), 0)
        self.assertEqual(self._stock(), Decimal("9"))

    def test_permite_corregir_cantidad_y_reintentar(self):
        with patch("ui.pos_widget.get_session", self.fake_get_session), \
             patch("ui.pos_widget.QMessageBox.warning") as aviso, \
             patch("ui.pos_widget.generar_ticket_pdf", return_value=None):
            # Primer intento: 10 sobre stock 9 → rechazado, diálogo sigue abierto.
            self.dlg._confirmar()
            self.assertFalse(self.dlg.venta_confirmada)
            self.assertEqual(aviso.call_count, 1)

            # El cajero corrige la cantidad y reintenta.
            self.dlg.items = [{"producto": self.prod, "cantidad": Decimal("9")}]
            self.dlg.total = Decimal("90.00")
            self.dlg._confirmar()

        self.assertTrue(self.dlg.venta_confirmada)
        self.assertEqual(self._ventas(), 1)
        self.assertEqual(self._stock(), Decimal("0"))

    def test_no_genera_ventas_duplicadas_tras_reintento(self):
        with patch("ui.pos_widget.get_session", self.fake_get_session), \
             patch("ui.pos_widget.QMessageBox.warning"), \
             patch("ui.pos_widget.generar_ticket_pdf", return_value=None):
            self.dlg._confirmar()  # rechazado
            self.dlg.items = [{"producto": self.prod, "cantidad": Decimal("9")}]
            self.dlg._confirmar()  # aceptado
            self.dlg._confirmar()  # doble clic / doble Enter
            self.dlg._confirmar()

        self.assertEqual(self._ventas(), 1)
        self.assertEqual(self._stock(), Decimal("0"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
