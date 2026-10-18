"""
services/compra_service.py – Lógica de negocio para compras.

Al registrar una compra:
  1. Crear cabecera Compra
  2. Crear DetalleCompra por cada ítem
  3. Sumar stock al Producto
  4. Actualizar precio_compra_bs del Producto al nuevo precio
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from models.compra import Compra, DetalleCompra
from models.producto import Producto

if TYPE_CHECKING:
    from models.usuario import Usuario
    from models.proveedor import Proveedor


def registrar_compra(
    session: Session,
    usuario: "Usuario",
    proveedor: "Proveedor",
    numero_factura: str,
    items: list[dict],        # [{"producto": Producto, "cantidad": Decimal, "precio_unitario_bs": Decimal}]
    observacion: str | None = None,
    actualizar_precio_compra: bool = True,
) -> Compra:
    """
    Registra una compra completa en una sola transacción.

    :param session:                Sesión SQLAlchemy activa.
    :param usuario:                Usuario que registra.
    :param proveedor:              Proveedor de la compra.
    :param numero_factura:         Número de factura del proveedor.
    :param items:                  Lista de dicts con 'producto', 'cantidad' y 'precio_unitario_bs'.
    :param observacion:            Nota libre.
    :param actualizar_precio_compra: Si True, actualiza precio_compra_bs en el producto.
    :returns:                      Compra creada.
    """
    # 1. Crear cabecera
    compra = Compra(
        numero_factura=numero_factura,
        fecha=datetime.now(),
        observacion=observacion,
        usuario_id=usuario.id,
        proveedor_id=proveedor.id,
    )
    session.add(compra)
    session.flush()

    # 2. Crear detalles, sumar stock y actualizar precio
    for item in items:
        prod: Producto = item["producto"]
        cant: Decimal  = Decimal(str(item["cantidad"]))
        precio: Decimal = Decimal(str(item["precio_unitario_bs"]))

        detalle = DetalleCompra(compra_id=compra.id, producto_id=prod.id)
        detalle.cantidad           = cant
        detalle.precio_unitario_bs = precio
        session.add(detalle)

        prod.stock_actual = prod.stock_actual + cant

        if actualizar_precio_compra:
            prod.precio_compra_bs = precio

    return compra
