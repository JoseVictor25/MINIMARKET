"""
services/reporte_service.py – Lógica de analítica, estadísticas y generación de informes de ventas.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from config import APP_NAME, CURRENCY
from models.venta import Venta, DetalleVenta
from models.producto import Producto
from models.categoria import Categoria
from models.usuario import Usuario


def _parse_mixto(obs: str | None) -> tuple[Decimal, Decimal]:
    """Extrae montos de QR y Efectivo desde la nota de un pago mixto."""
    if not obs:
        return Decimal("0.00"), Decimal("0.00")
    match = re.search(r"QR Bs\s*([\d\.]+)\s*\+\s*Efectivo Bs\s*([\d\.]+)", obs, re.IGNORECASE)
    if match:
        try:
            return Decimal(match.group(1)), Decimal(match.group(2))
        except Exception:
            pass
    return Decimal("0.00"), Decimal("0.00")


def obtener_metricas_generales(
    session: Session,
    fecha_inicio: datetime,
    fecha_fin: datetime,
    usuario_id: int | None = None,
) -> dict:
    """Calcula las métricas e indicadores clave de rendimiento (KPIs) en el período."""
    query = (
        session.query(Venta)
        .filter(Venta.fecha >= fecha_inicio, Venta.fecha <= fecha_fin)
        .filter(Venta.estado == Venta.ESTADO_COMPLETADA)
    )
    if usuario_id:
        query = query.filter(Venta.usuario_id == usuario_id)

    ventas = query.all()

    total_ventas = Decimal("0.00")
    costo_total = Decimal("0.00")
    unidades_vendidas = Decimal("0.00")

    for v in ventas:
        total_ventas += v.total_bs
        for d in v.detalles:
            cant = d.cantidad
            unidades_vendidas += cant
            p_compra = d.producto.precio_compra_bs if d.producto else Decimal("0.00")
            costo_total += cant * p_compra

    cant_transacciones = len(ventas)
    ticket_promedio = (total_ventas / cant_transacciones) if cant_transacciones > 0 else Decimal("0.00")
    ganancia_estimada = total_ventas - costo_total
    margen_porcentaje = (ganancia_estimada / total_ventas * Decimal("100.00")) if total_ventas > Decimal("0.00") else Decimal("0.00")

    return {
        "total_ventas": total_ventas,
        "costo_total": costo_total,
        "ganancia_estimada": ganancia_estimada,
        "margen_porcentaje": margen_porcentaje,
        "cant_transacciones": cant_transacciones,
        "unidades_vendidas": unidades_vendidas,
        "ticket_promedio": ticket_promedio,
    }


def obtener_ventas_cronologicas(
    session: Session,
    fecha_inicio: datetime,
    fecha_fin: datetime,
    usuario_id: int | None = None,
) -> list[dict]:
    """
    Agrupa ventas por fecha (o por hora si el rango es del mismo día)
    para alimentar gráficos o barras de tendencia.
    """
    query = (
        session.query(Venta)
        .filter(Venta.fecha >= fecha_inicio, Venta.fecha <= fecha_fin)
        .filter(Venta.estado == Venta.ESTADO_COMPLETADA)
    )
    if usuario_id:
        query = query.filter(Venta.usuario_id == usuario_id)

    ventas = query.order_by(Venta.fecha.asc()).all()

    mismo_dia = (fecha_inicio.date() == fecha_fin.date())
    agrupado: dict[str, dict] = {}

    for v in ventas:
        if mismo_dia:
            clave = v.fecha.strftime("%H:00")
        else:
            clave = v.fecha.strftime("%d/%m")

        if clave not in agrupado:
            agrupado[clave] = {
                "label": clave,
                "total": Decimal("0.00"),
                "cantidad": 0,
            }
        agrupado[clave]["total"] += v.total_bs
        agrupado[clave]["cantidad"] += 1

    return list(agrupado.values())


def obtener_top_productos(
    session: Session,
    fecha_inicio: datetime,
    fecha_fin: datetime,
    limite: int = 10,
    usuario_id: int | None = None,
) -> list[dict]:
    """Retorna los productos con mayor recaudación y unidades vendidas en el período."""
    query = (
        session.query(Venta)
        .filter(Venta.fecha >= fecha_inicio, Venta.fecha <= fecha_fin)
        .filter(Venta.estado == Venta.ESTADO_COMPLETADA)
    )
    if usuario_id:
        query = query.filter(Venta.usuario_id == usuario_id)

    ventas = query.all()
    conteo: dict[int, dict] = {}

    for v in ventas:
        for d in v.detalles:
            pid = d.producto_id
            cant = d.cantidad
            subt = d.subtotal_bs
            costo = cant * (d.producto.precio_compra_bs if d.producto else Decimal("0.00"))

            if pid not in conteo:
                p = d.producto
                conteo[pid] = {
                    "producto_id": pid,
                    "codigo": p.codigo_barras if p else "-",
                    "descripcion": p.descripcion if p else "Producto Eliminado",
                    "categoria": p.categoria.nombre if (p and p.categoria) else "General",
                    "cantidad": Decimal("0.00"),
                    "total": Decimal("0.00"),
                    "costo": Decimal("0.00"),
                    "ganancia": Decimal("0.00"),
                }
            conteo[pid]["cantidad"] += cant
            conteo[pid]["total"] += subt
            conteo[pid]["costo"] += costo
            conteo[pid]["ganancia"] += (subt - costo)

    lista = list(conteo.values())
    lista.sort(key=lambda x: x["total"], reverse=True)
    return lista[:limite]


def obtener_desglose_metodos_pago(
    session: Session,
    fecha_inicio: datetime,
    fecha_fin: datetime,
    usuario_id: int | None = None,
) -> list[dict]:
    """Desglosa la recaudación total por método de pago real (desglosando pagos mixtos)."""
    query = (
        session.query(Venta)
        .filter(Venta.fecha >= fecha_inicio, Venta.fecha <= fecha_fin)
        .filter(Venta.estado == Venta.ESTADO_COMPLETADA)
    )
    if usuario_id:
        query = query.filter(Venta.usuario_id == usuario_id)

    ventas = query.all()

    totales = {
        "efectivo": {"nombre": "Efectivo", "monto": Decimal("0.00"), "transacciones": 0, "color": "#22c55e"},
        "qr":       {"nombre": "Transferencia QR", "monto": Decimal("0.00"), "transacciones": 0, "color": "#3b82f6"},
        "tarjeta":  {"nombre": "Tarjeta Débito/Crédito", "monto": Decimal("0.00"), "transacciones": 0, "color": "#a855f7"},
        "otros":    {"nombre": "Otros Medios", "monto": Decimal("0.00"), "transacciones": 0, "color": "#f59e0b"},
    }

    total_general = Decimal("0.00")

    for v in ventas:
        metodo = (v.metodo_pago or "").lower()
        subt = v.total_bs
        total_general += subt

        if metodo == "efectivo":
            totales["efectivo"]["monto"] += subt
            totales["efectivo"]["transacciones"] += 1
        elif metodo == "qr":
            totales["qr"]["monto"] += subt
            totales["qr"]["transacciones"] += 1
        elif metodo == "tarjeta":
            totales["tarjeta"]["monto"] += subt
            totales["tarjeta"]["transacciones"] += 1
        elif metodo == "mixto":
            mqr, mef = _parse_mixto(v.observacion)
            if mqr > 0 or mef > 0:
                totales["qr"]["monto"] += mqr
                totales["efectivo"]["monto"] += mef
            else:
                totales["efectivo"]["monto"] += subt
            totales["efectivo"]["transacciones"] += 1
            totales["qr"]["transacciones"] += 1
        else:
            totales["otros"]["monto"] += subt
            totales["otros"]["transacciones"] += 1

    resultado = []
    for k, info in totales.items():
        m = info["monto"]
        pct = (m / total_general * 100) if total_general > 0 else Decimal("0.00")
        resultado.append({
            "metodo": k,
            "nombre": info["nombre"],
            "monto": m,
            "transacciones": info["transacciones"],
            "porcentaje": pct,
            "color": info["color"],
        })

    return resultado


def obtener_rendimiento_cajeros(
    session: Session,
    fecha_inicio: datetime,
    fecha_fin: datetime,
) -> list[dict]:
    """Calcula las ventas y desempeño por cada cajero en el período."""
    ventas = (
        session.query(Venta)
        .filter(Venta.fecha >= fecha_inicio, Venta.fecha <= fecha_fin)
        .filter(Venta.estado == Venta.ESTADO_COMPLETADA)
        .all()
    )

    cajeros: dict[int, dict] = {}
    total_gral = Decimal("0.00")

    for v in ventas:
        uid = v.usuario_id
        tot = v.total_bs
        total_gral += tot

        if uid not in cajeros:
            u = v.usuario
            cajeros[uid] = {
                "usuario_id": uid,
                "nombre": u.nombre_completo if u else "Desconocido",
                "username": u.username if u else "-",
                "total": Decimal("0.00"),
                "transacciones": 0,
            }
        cajeros[uid]["total"] += tot
        cajeros[uid]["transacciones"] += 1

    lista = list(cajeros.values())
    for item in lista:
        t_cajero = item["total"]
        item["ticket_promedio"] = (t_cajero / item["transacciones"]) if item["transacciones"] > 0 else Decimal("0.00")
        item["porcentaje"] = (t_cajero / total_gral * 100) if total_gral > 0 else Decimal("0.00")

    lista.sort(key=lambda x: x["total"], reverse=True)
    return lista


def generar_reporte_pdf(
    session: Session,
    fecha_inicio: datetime,
    fecha_fin: datetime,
    usuario_id: int | None = None,
    destino: Path | None = None,
) -> Path:
    """
    Genera un informe ejecutivo formal en formato A4 con ReportLab,
    incluyendo KPIs, formas de pago, ranking de productos y rendimiento.
    """
    if destino is None:
        rep_dir = Path("reportes")
        rep_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = rep_dir / f"reporte_ventas_{ts}.pdf"

    metricas = obtener_metricas_generales(session, fecha_inicio, fecha_fin, usuario_id)
    pagos = obtener_desglose_metodos_pago(session, fecha_inicio, fecha_fin, usuario_id)
    top_prods = obtener_top_productos(session, fecha_inicio, fecha_fin, limite=10, usuario_id=usuario_id)
    cajeros = obtener_rendimiento_cajeros(session, fecha_inicio, fecha_fin)

    doc = SimpleDocTemplate(
        str(destino),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    styles = getSampleStyleSheet()
    primary_color = colors.HexColor("#1e293b")
    accent_color = colors.HexColor("#2563eb")
    border_color = colors.HexColor("#cbd5e1")

    # Estilos de texto
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=primary_color,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748b"),
    )
    sec_title_style = ParagraphStyle(
        "SecTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=accent_color,
    )
    cell_bold = ParagraphStyle("CellB", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=primary_color)
    cell_norm = ParagraphStyle("CellN", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#334155"))
    cell_right = ParagraphStyle("CellR", fontName="Helvetica", fontSize=8.5, leading=11, alignment=2, textColor=colors.HexColor("#334155"))
    cell_right_b = ParagraphStyle("CellRB", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=2, textColor=primary_color)

    elements = []

    # ── Encabezado ────────────────────────────────────────────────────────────
    rango_txt = f"{fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}"
    header_data = [
        [
            Paragraph(f"<b>{APP_NAME}</b><br/><font size=13 color='#2563eb'>Informe Estadístico de Ventas</font>", title_style),
            Paragraph(f"<b>Período:</b> {rango_txt}<br/><b>Emisión:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style),
        ]
    ]
    t_hdr = Table(header_data, colWidths=[110 * mm, 72 * mm])
    t_hdr.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    elements.append(t_hdr)
    elements.append(Spacer(1, 6 * mm))

    # ── Bloque de Indicadores Clave (KPIs) ───────────────────────────────────
    kpi_data = [
        [
            Paragraph("<b>TOTAL FACTURADO</b>", cell_bold),
            Paragraph("<b>UTILIDAD ESTIMADA</b>", cell_bold),
            Paragraph("<b>TICKET PROMEDIO</b>", cell_bold),
            Paragraph("<b>OPERACIONES</b>", cell_bold),
        ],
        [
            Paragraph(f"<font size=13 color='#15803d'><b>{CURRENCY} {metricas['total_ventas']:.2f}</b></font>", cell_norm),
            Paragraph(f"<font size=13 color='#2563eb'><b>{CURRENCY} {metricas['ganancia_estimada']:.2f}</b></font><br/><font size=7 color='#64748b'>Margen: {metricas['margen_porcentaje']:.1f}%</font>", cell_norm),
            Paragraph(f"<font size=13 color='#0f172a'><b>{CURRENCY} {metricas['ticket_promedio']:.2f}</b></font>", cell_norm),
            Paragraph(f"<font size=13 color='#0f172a'><b>{metricas['cant_transacciones']} ventas</b></font><br/><font size=7 color='#64748b'>{metricas['unidades_vendidas']:.0f} unidades</font>", cell_norm),
        ],
    ]
    t_kpis = Table(kpi_data, colWidths=[45 * mm, 46 * mm, 45 * mm, 46 * mm])
    t_kpis.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ('BOX', (0,0), (-1,-1), 1, border_color),
        ('INNERGRID', (0,0), (-1,-1), 0.5, border_color),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    elements.append(t_kpis)
    elements.append(Spacer(1, 6 * mm))

    # ── Tabla de Formas de Pago ───────────────────────────────────────────────
    elements.append(Paragraph("Desglose por Método de Pago", sec_title_style))
    elements.append(Spacer(1, 2 * mm))

    pago_rows = [
        [Paragraph("<b>Método de Pago</b>", cell_bold), Paragraph("<b>N° Operaciones</b>", cell_right_b), Paragraph("<b>Total Recaudado</b>", cell_right_b), Paragraph("<b>Participación %</b>", cell_right_b)]
    ]
    for p in pagos:
        pago_rows.append([
            Paragraph(p["nombre"], cell_norm),
            Paragraph(str(p["transacciones"]), cell_right),
            Paragraph(f"{CURRENCY} {p['monto']:.2f}", cell_right),
            Paragraph(f"{p['porcentaje']:.1f}%", cell_right),
        ])
    t_pagos = Table(pago_rows, colWidths=[70 * mm, 36 * mm, 40 * mm, 36 * mm])
    t_pagos.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f1f5f9")),
        ('BOX', (0,0), (-1,-1), 0.5, border_color),
        ('INNERGRID', (0,0), (-1,-1), 0.5, border_color),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(t_pagos)
    elements.append(Spacer(1, 6 * mm))

    # ── Top 10 Productos Más Vendidos ─────────────────────────────────────────
    elements.append(Paragraph("Top 10 Productos Más Vendidos", sec_title_style))
    elements.append(Spacer(1, 2 * mm))

    prod_rows = [
        [
            Paragraph("<b>#</b>", cell_bold),
            Paragraph("<b>Código</b>", cell_bold),
            Paragraph("<b>Descripción del Producto</b>", cell_bold),
            Paragraph("<b>Categoría</b>", cell_bold),
            Paragraph("<b>Cant.</b>", cell_right_b),
            Paragraph("<b>Total Venta</b>", cell_right_b),
            Paragraph("<b>Ganancia</b>", cell_right_b),
        ]
    ]
    for i, pr in enumerate(top_prods, start=1):
        prod_rows.append([
            Paragraph(str(i), cell_norm),
            Paragraph(pr["codigo"], cell_norm),
            Paragraph(pr["descripcion"][:28], cell_norm),
            Paragraph(pr["categoria"][:14], cell_norm),
            Paragraph(f"{pr['cantidad']:.0f}", cell_right),
            Paragraph(f"{CURRENCY} {pr['total']:.2f}", cell_right),
            Paragraph(f"{CURRENCY} {pr['ganancia']:.2f}", cell_right),
        ])

    t_prods = Table(prod_rows, colWidths=[8 * mm, 26 * mm, 62 * mm, 28 * mm, 16 * mm, 22 * mm, 20 * mm])
    t_prods.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f1f5f9")),
        ('BOX', (0,0), (-1,-1), 0.5, border_color),
        ('INNERGRID', (0,0), (-1,-1), 0.5, border_color),
        ('TOPPADDING', (0,0), (-1,-1), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
    ]))
    elements.append(t_prods)

    # ── Firmas / Pie ──────────────────────────────────────────────────────────
    elements.append(Spacer(1, 10 * mm))
    firmas_data = [
        [
            Paragraph("____________________________<br/>Firma Administrador / Gerente", cell_bold),
            Paragraph("____________________________<br/>Firma Auditoría / Control", cell_bold),
        ]
    ]
    t_firmas = Table(firmas_data, colWidths=[91 * mm, 91 * mm])
    t_firmas.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(KeepTogether(t_firmas))

    doc.build(elements)
    return destino


def exportar_ventas_csv(
    session: Session,
    fecha_inicio: datetime,
    fecha_fin: datetime,
    usuario_id: int | None = None,
    destino: Path | None = None,
) -> Path:
    """Exporta el detalle de todas las ventas del período a formato CSV compatible con Excel."""
    if destino is None:
        rep_dir = Path("reportes")
        rep_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = rep_dir / f"export_ventas_{ts}.csv"

    query = (
        session.query(Venta)
        .filter(Venta.fecha >= fecha_inicio, Venta.fecha <= fecha_fin)
        .filter(Venta.estado == Venta.ESTADO_COMPLETADA)
        .order_by(Venta.fecha.desc())
    )
    if usuario_id:
        query = query.filter(Venta.usuario_id == usuario_id)

    ventas = query.all()

    with open(str(destino), mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        # Encabezado
        writer.writerow([
            "Nro_Transaccion", "Fecha", "Hora", "Cajero",
            "Cliente_NIT", "Cliente_RazonSocial", "Metodo_Pago",
            "Codigo_Barras", "Descripcion_Producto", "Cantidad",
            "Precio_Unitario_Bs", "Subtotal_Bs", "Total_Venta_Bs"
        ])

        for v in ventas:
            f_fecha = v.fecha.strftime("%d/%m/%Y")
            f_hora = v.fecha.strftime("%H:%M:%S")
            cajero = v.usuario.username if v.usuario else "Desconocido"
            nit = v.cliente.nit if v.cliente else "0"
            cliente = v.cliente.razon_social if v.cliente else "Público General"
            metodo = v.metodo_pago
            total_v = f"{v.total_bs:.2f}"

            for d in v.detalles:
                prod = d.producto
                cod = prod.codigo_barras if prod else ""
                desc = prod.descripcion if prod else ""
                cant = f"{d.cantidad:.3f}"
                pu = f"{d.precio_unitario_bs:.2f}"
                sub = f"{d.subtotal_bs:.2f}"

                writer.writerow([
                    v.numero_transaccion, f_fecha, f_hora, cajero,
                    nit, cliente, metodo, cod, desc, cant, pu, sub, total_v
                ])

    return destino
