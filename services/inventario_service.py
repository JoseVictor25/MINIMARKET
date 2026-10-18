"""
services/inventario_service.py – Ajustes manuales y consultas de stock.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from models.ajuste_inventario import AjusteInventario
from models.producto import Producto

if TYPE_CHECKING:
    from models.usuario import Usuario


def ajustar_stock(
    session: Session,
    usuario: "Usuario",
    producto: Producto,
    cantidad: Decimal,
    tipo: str,
    motivo: str,
) -> AjusteInventario:
    """
    Realiza un ajuste manual de inventario.

    :param tipo:    AjusteInventario.TIPO_ENTRADA o TIPO_SALIDA
    :param motivo:  Razón del ajuste (obligatorio)
    :raises ValueError: Si tipo inválido o stock resultante negativo.
    """
    if tipo not in (AjusteInventario.TIPO_ENTRADA, AjusteInventario.TIPO_SALIDA):
        raise ValueError(f"Tipo de ajuste inválido: {tipo}")

    cant = Decimal(str(cantidad))

    if tipo == AjusteInventario.TIPO_SALIDA:
        if producto.stock_actual < cant:
            raise ValueError(
                f"Stock insuficiente para ajuste de salida: "
                f"disponible={producto.stock_actual}, requerido={cant}"
            )
        producto.stock_actual = producto.stock_actual - cant
    else:
        producto.stock_actual = producto.stock_actual + cant

    ajuste = AjusteInventario(
        tipo=tipo,
        motivo=motivo,
        producto_id=producto.id,
        usuario_id=usuario.id,
    )
    ajuste.cantidad = cant
    session.add(ajuste)
    return ajuste


def productos_con_stock_bajo(session: Session) -> list[Producto]:
    """Retorna todos los productos cuyo stock_actual <= stock_minimo."""
    return [
        p for p in session.query(Producto).filter(Producto.activo == True).all()
        if p.stock_bajo
    ]
