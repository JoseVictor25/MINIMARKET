"""
services/caja_service.py – Lógica de negocio para Control de Caja (Apertura, Cierre y Arqueo).
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from config import APP_NAME, CURRENCY
from models.caja import SesionCaja
from models.venta import Venta

if TYPE_CHECKING:
    from models.usuario import Usuario

THERMAL_WIDTH = 80 * mm


class CajaYaAbiertaError(Exception):
    """Se lanza cuando el usuario ya tiene una caja abierta.

    Guarda una instantánea de datos primitivos (no objetos ORM) para que la
    interfaz pueda informar el conflicto incluso después de cerrar la sesión.
    """

    def __init__(self, cajas: list[SesionCaja]):
        self.cajas = [
            SimpleNamespace(
                id=c.id,
                turno=c.turno,
                usuario_id=c.usuario_id,
                monto_inicial_bs=c.monto_inicial_bs,
            )
            for c in cajas
        ]
        ids = ", ".join(f"#{c.id}" for c in self.cajas)
        super().__init__(
            f"El usuario ya tiene {len(self.cajas)} caja(s) abierta(s): {ids}. "
            "Debe continuar con la caja existente o cerrarla antes de abrir otra."
        )


class CajaNoAutorizadaError(Exception):
    """Se lanza cuando un usuario intenta operar una caja que no le pertenece."""


def cajas_abiertas_usuario(session: Session, usuario_id: int) -> list[SesionCaja]:
    """Retorna las cajas abiertas de un usuario, de la más reciente a la más antigua."""
    return (
        session.query(SesionCaja)
        .filter(
            SesionCaja.estado == SesionCaja.ESTADO_ABIERTA,
            SesionCaja.usuario_id == usuario_id,
        )
        .order_by(SesionCaja.id.desc())
        .all()
    )


def cajas_abiertas(session: Session) -> list[SesionCaja]:
    """Retorna todas las cajas abiertas del sistema (consulta de supervisión)."""
    return (
        session.query(SesionCaja)
        .filter(SesionCaja.estado == SesionCaja.ESTADO_ABIERTA)
        .order_by(SesionCaja.id.desc())
        .all()
    )


def obtener_caja_activa(session: Session, usuario_id: int) -> SesionCaja | None:
    """
    Obtiene la caja operativa de un usuario.

    Siempre filtra por usuario y estado abierto. No existe una búsqueda
    implícita de la caja de otro usuario: para supervisión administrativa
    deben usarse explícitamente cajas_abiertas() o cajas_abiertas_usuario().
    """
    if usuario_id is None:
        raise ValueError("obtener_caja_activa requiere el usuario_id del propietario.")
    return (
        session.query(SesionCaja)
        .filter(
            SesionCaja.estado == SesionCaja.ESTADO_ABIERTA,
            SesionCaja.usuario_id == usuario_id,
        )
        .order_by(SesionCaja.id.desc())
        .first()
    )


def abrir_caja(
    session: Session,
    usuario_id: int,
    turno: str = "Mañana",
    monto_inicial_bs: Decimal | float | str = Decimal("0.00"),
    fecha_apertura: datetime | None = None,
    observacion: str | None = None,
) -> SesionCaja:
    """
    Abre una nueva sesión de caja para un usuario.

    Regla de negocio: un usuario no puede tener más de una caja abierta.
    No se cierran ni modifican cajas existentes automáticamente.
    """
    existentes = cajas_abiertas_usuario(session, usuario_id)
    if existentes:
        raise CajaYaAbiertaError(existentes)

    monto_dec = Decimal(str(monto_inicial_bs or "0.00"))

    nueva_caja = SesionCaja(
        usuario_id=usuario_id,
        turno=turno,
        fecha_apertura=fecha_apertura or datetime.now(),
        estado=SesionCaja.ESTADO_ABIERTA,
        observacion=observacion,
    )
    nueva_caja.monto_inicial_bs = monto_dec

    session.add(nueva_caja)
    session.flush()
    return nueva_caja


def obtener_resumen_caja(session: Session, sesion_caja_id: int) -> dict:
    """
    Calcula los totales y desglose de formas de pago para una sesión de caja.
    """
    sesion = session.get(SesionCaja, sesion_caja_id)
    if not sesion:
        raise ValueError(f"No existe sesión de caja #{sesion_caja_id}")

    ventas = (
        session.query(Venta)
        .filter(Venta.sesion_caja_id == sesion_caja_id, Venta.estado == Venta.ESTADO_COMPLETADA)
        .all()
    )

    ventas_efectivo = Decimal("0.00")
    ventas_qr = Decimal("0.00")
    ventas_tarjeta = Decimal("0.00")
    ventas_otros = Decimal("0.00")

    for v in ventas:
        metodo = (v.metodo_pago or "").lower()
        if metodo == "efectivo":
            ventas_efectivo += v.total_bs
        elif metodo == "qr":
            ventas_qr += v.total_bs
        elif metodo == "tarjeta":
            ventas_tarjeta += v.total_bs
        elif metodo == "mixto":
            # Desglosar observación: Pago Mixto: QR Bs XX.XX + Efectivo Bs YY.YY
            obs = v.observacion or ""
            match = re.search(r"QR Bs\s*([\d\.]+)\s*\+\s*Efectivo Bs\s*([\d\.]+)", obs, re.IGNORECASE)
            if match:
                try:
                    q_val = Decimal(match.group(1))
                    e_val = Decimal(match.group(2))
                    ventas_qr += q_val
                    ventas_efectivo += e_val
                except Exception:
                    ventas_efectivo += v.total_bs
            else:
                ventas_efectivo += v.total_bs
        else:
            ventas_otros += v.total_bs

    total_ventas = ventas_efectivo + ventas_qr + ventas_tarjeta + ventas_otros
    base_inicial = sesion.monto_inicial_bs
    total_efectivo_esperado = base_inicial + ventas_efectivo

    return {
        "sesion_id": sesion.id,
        "usuario_id": sesion.usuario_id,
        "usuario_nombre": sesion.usuario.nombre_completo if sesion.usuario else "Desconocido",
        "usuario_username": sesion.usuario.username if sesion.usuario else "",
        "turno": sesion.turno,
        "fecha_apertura": sesion.fecha_apertura,
        "fecha_cierre": sesion.fecha_cierre,
        "estado": sesion.estado,
        "base_inicial": base_inicial,
        "ventas_efectivo": ventas_efectivo,
        "ventas_qr": ventas_qr,
        "ventas_tarjeta": ventas_tarjeta,
        "ventas_otros": ventas_otros,
        "total_ventas": total_ventas,
        "total_efectivo_esperado": total_efectivo_esperado,
        "cantidad_ventas": len(ventas),
    }


def cerrar_caja(
    session: Session,
    sesion_caja_id: int,
    monto_fisico_bs: Decimal | float | str,
    observacion: str | None = None,
    *,
    usuario_id: int,
) -> tuple[SesionCaja, dict]:
    """
    Cierra la sesión de caja registrando el arqueo físico y calculando sobrante/faltante.

    Solo el propietario de la caja puede cerrarla. No se implementa cierre
    forzado de cajas ajenas desde el flujo normal.
    """
    sesion = session.get(SesionCaja, sesion_caja_id)
    if not sesion:
        raise ValueError(f"No existe sesión de caja #{sesion_caja_id}")
    if usuario_id is None:
        raise CajaNoAutorizadaError("Se requiere el usuario autenticado para cerrar una caja.")
    if sesion.usuario_id != usuario_id:
        raise CajaNoAutorizadaError(
            f"La caja #{sesion_caja_id} pertenece a otro usuario y no puede cerrarse desde este flujo."
        )
    if sesion.estado != SesionCaja.ESTADO_ABIERTA:
        raise ValueError(f"La caja #{sesion_caja_id} no está abierta.")

    resumen = obtener_resumen_caja(session, sesion_caja_id)
    monto_fisico_dec = Decimal(str(monto_fisico_bs or "0.00"))
    diferencia = monto_fisico_dec - resumen["total_efectivo_esperado"]

    sesion.fecha_cierre = datetime.now()
    sesion.monto_final_efectivo_bs = monto_fisico_dec
    sesion.diferencia_bs = diferencia
    sesion.estado = SesionCaja.ESTADO_CERRADA
    if observacion:
        sesion.observacion = observacion

    session.flush()
    return sesion, resumen


def generar_ticket_arqueo_pdf(
    session: Session,
    sesion_caja_id: int,
    destino: Path | None = None,
) -> Path:
    """
    Genera un comprobante térmico (80mm) con el detalle del arqueo y cierre de caja.
    """
    resumen = obtener_resumen_caja(session, sesion_caja_id)
    sesion = session.get(SesionCaja, sesion_caja_id)

    if destino is None:
        tickets_dir = Path("tickets")
        tickets_dir.mkdir(parents=True, exist_ok=True)
        destino = tickets_dir / f"arqueo_caja_{sesion_caja_id}.pdf"

    # Altura del ticket
    altura = 190 * mm
    c = canvas.Canvas(str(destino), pagesize=(THERMAL_WIDTH, altura))

    y = altura - 8 * mm
    ancho = THERMAL_WIDTH - 6 * mm
    cx = THERMAL_WIDTH / 2

    def nl(pasos=1):
        nonlocal y
        y -= pasos * 4.5 * mm

    # Encabezado
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(cx, y, APP_NAME)
    nl()
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(cx, y, "CONTROL Y ARQUEO DE CAJA")
    nl()
    c.setFont("Helvetica", 8)
    c.drawCentredString(cx, y, f"Sesión #{sesion.id} - Turno: {sesion.turno}")
    nl()
    c.drawCentredString(cx, y, datetime.now().strftime("%d/%m/%Y %H:%M"))
    nl()

    c.setLineWidth(0.5)
    c.line(3 * mm, y, THERMAL_WIDTH - 3 * mm, y)
    nl()

    # Datos Generales
    c.setFont("Helvetica", 8)
    c.drawString(4 * mm, y, f"Cajero: {resumen['usuario_nombre']} ({resumen['usuario_username']})")
    nl()
    f_ap = resumen['fecha_apertura'].strftime("%d/%m/%Y %H:%M") if resumen['fecha_apertura'] else "-"
    c.drawString(4 * mm, y, f"Apertura: {f_ap}")
    nl()
    f_ci = resumen['fecha_cierre'].strftime("%d/%m/%Y %H:%M") if resumen['fecha_cierre'] else datetime.now().strftime("%d/%m/%Y %H:%M")
    c.drawString(4 * mm, y, f"Cierre:   {f_ci}")
    nl()
    c.drawString(4 * mm, y, f"Transacciones: {resumen['cantidad_ventas']} ventas")
    nl()

    c.line(3 * mm, y, THERMAL_WIDTH - 3 * mm, y)
    nl()

    # Desglose de ingresos
    def fila(label: str, valor: Decimal, negrita: bool = False):
        if negrita:
            c.setFont("Helvetica-Bold", 8.5)
        else:
            c.setFont("Helvetica", 8)
        c.drawString(4 * mm, y, label)
        c.drawRightString(THERMAL_WIDTH - 4 * mm, y, f"{CURRENCY} {valor:.2f}")
        nl()

    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(4 * mm, y, "DESGLOSE DE VENTAS")
    nl()
    fila("(+) Base Apertura:", resumen["base_inicial"])
    fila("(+) Ventas Efectivo:", resumen["ventas_efectivo"])
    fila("    Ventas QR:", resumen["ventas_qr"])
    fila("    Ventas Tarjeta:", resumen["ventas_tarjeta"])
    if resumen["ventas_otros"] > 0:
        fila("    Otros Medios:", resumen["ventas_otros"])

    c.line(3 * mm, y, THERMAL_WIDTH - 3 * mm, y)
    nl()
    fila("TOTAL VENTAS:", resumen["total_ventas"], negrita=True)
    nl(0.5)

    c.line(3 * mm, y, THERMAL_WIDTH - 3 * mm, y)
    nl()

    # Resumen Arqueo
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(4 * mm, y, "ARQUEO DE EFECTIVO")
    nl()
    fila("Efectivo Esperado:", resumen["total_efectivo_esperado"], negrita=True)

    monto_fisico = sesion.monto_final_efectivo_bs if sesion.monto_final_efectivo_bs is not None else resumen["total_efectivo_esperado"]
    diferencia = sesion.diferencia_bs if sesion.diferencia_bs is not None else (monto_fisico - resumen["total_efectivo_esperado"])

    fila("Efectivo Físico Contado:", monto_fisico, negrita=True)

    if diferencia == 0:
        estado_dif = "Diferencia: Bs 0.00 (CUADRADA)"
    elif diferencia > 0:
        estado_dif = f"Diferencia: +Bs {diferencia:.2f} (SOBRANTE)"
    else:
        estado_dif = f"Diferencia: -Bs {abs(diferencia):.2f} (FALTANTE)"

    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(cx, y, estado_dif)
    nl(2)

    # Firmas
    c.line(8 * mm, y, 36 * mm, y)
    c.line(44 * mm, y, 72 * mm, y)
    nl()
    c.setFont("Helvetica", 7)
    c.drawCentredString(22 * mm, y, "Firma Cajero")
    c.drawCentredString(58 * mm, y, "Firma Supervisor")
    nl(2)

    c.drawCentredString(cx, y, "*** REPORTE OFICIAL DE CAJA ***")

    c.save()
    return destino
