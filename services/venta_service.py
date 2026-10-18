"""
services/venta_service.py – Lógica de negocio para ventas.

Toda la operación se ejecuta en UNA transacción:
  1. Crear cabecera Venta
  2. Crear DetalleVenta por cada ítem
  3. Descontar stock de cada Producto

La anulación revierte el stock y marca la venta como anulada.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from models.venta import Venta, DetalleVenta
from models.producto import Producto

if TYPE_CHECKING:
    from models.usuario import Usuario
    from models.cliente import Cliente


class StockInsuficienteError(Exception):
    """Se lanza cuando un producto no tiene stock suficiente."""
    def __init__(self, producto: Producto, disponible: Decimal, requerido: Decimal):
        self.producto = producto
        self.disponible = disponible
        self.requerido = requerido
        super().__init__(
            f"Stock insuficiente para '{producto.descripcion}': "
            f"disponible={disponible}, requerido={requerido}"
        )


def _siguiente_numero_transaccion(session: Session) -> int:
    """Genera el siguiente número de transacción correlativo."""
    ultimo = session.query(Venta).order_by(Venta.numero_transaccion.desc()).first()
    return (ultimo.numero_transaccion + 1) if ultimo else 1


def registrar_venta(
    session: Session,
    usuario: "Usuario",
    items: list[dict],          # [{"producto": Producto, "cantidad": Decimal}]
    metodo_pago: str = "efectivo",
    cliente: "Cliente | None" = None,
    observacion: str | None = None,
    sesion_caja_id: int | None = None,
    qr_confirmado: bool = False,
    referencia_pago: str | None = None,
    comprobante_pago: str | None = None,
) -> Venta:
    """
    Registra una venta completa en una sola transacción.

    :param session:        Sesión SQLAlchemy activa (el llamador gestiona commit/rollback).
    :param usuario:        Usuario que registra la venta.
    :param items:          Lista de dicts con 'producto' y 'cantidad'.
    :param metodo_pago:    Método de pago ('efectivo', 'tarjeta', 'transferencia', 'qr', 'mixto').
    :param cliente:        Cliente opcional.
    :param observacion:    Nota libre.
    :param sesion_caja_id: ID de la sesión de caja activa vinculada.
    :param qr_confirmado:  Indica si el pago QR fue confirmado por el cajero.
    :param referencia_pago: Número de transacción o referencia del pago.
    :param comprobante_pago: Ruta a la imagen del comprobante adjunto.
    :returns:              Venta creada.
    :raises StockInsuficienteError: Si algún producto no tiene stock.
    """
    # 1. Validar stock antes de modificar nada
    for item in items:
        prod: Producto = item["producto"]
        cant: Decimal  = Decimal(str(item["cantidad"]))
        if prod.stock_actual < cant:
            raise StockInsuficienteError(prod, prod.stock_actual, cant)

    # 2. Crear cabecera
    venta = Venta(
        numero_transaccion=_siguiente_numero_transaccion(session),
        fecha=datetime.now(),
        estado=Venta.ESTADO_COMPLETADA,
        metodo_pago=metodo_pago,
        observacion=observacion,
        usuario_id=usuario.id,
        cliente_id=cliente.id if cliente else None,
        sesion_caja_id=sesion_caja_id,
        qr_confirmado=qr_confirmado,
        referencia_pago=referencia_pago,
        comprobante_pago=comprobante_pago,
    )
    session.add(venta)
    session.flush()  # Obtiene venta.id sin commit

    # 3. Crear detalles y descontar stock
    for item in items:
        prod: Producto = item["producto"]
        cant: Decimal  = Decimal(str(item["cantidad"]))

        detalle = DetalleVenta(venta_id=venta.id, producto_id=prod.id)
        detalle.cantidad          = cant
        detalle.precio_unitario_bs = prod.precio_venta_bs
        session.add(detalle)

        prod.stock_actual = prod.stock_actual - cant

    return venta


def anular_venta(
    session: Session,
    venta: Venta,
    motivo: str = "Sin motivo especificado",
) -> Venta:
    """
    Anula una venta y revierte el stock de todos los productos.
    Solo se pueden anular ventas con estado 'completada'.
    """
    if venta.estado != Venta.ESTADO_COMPLETADA:
        raise ValueError(f"No se puede anular una venta con estado '{venta.estado}'.")

    # Revertir stock
    for detalle in venta.detalles:
        prod = session.get(Producto, detalle.producto_id)
        if prod:
            prod.stock_actual = prod.stock_actual + detalle.cantidad

    venta.estado     = Venta.ESTADO_ANULADA
    venta.observacion = f"[ANULADA] {motivo}"
    return venta
