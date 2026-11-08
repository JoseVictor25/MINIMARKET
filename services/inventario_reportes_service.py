"""
services/inventario_reportes_service.py – Reportes exportables del módulo de
inventario: inventario completo, ganancias en ventas e historial de ajustes.

Se mantiene separado de ``export_service`` para no alterar las exportaciones
de compras, ventas y bajo stock que ya estaban validadas.
"""
from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Sequence

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from config import APP_NAME, CURRENCY
from models.producto import Producto
from services.export_service import NumberedCanvas, _cantidad_texto, _texto_pdf


def _num(valor, decimales: int = 2) -> str:
    """Formatea un número de forma segura para tablas y celdas."""
    try:
        return f"{Decimal(str(valor)):,.{decimales}f}"
    except Exception:
        return str(valor)


def _estado_stock_texto(producto: Producto) -> str:
    if producto.stock_actual <= 0:
        return "AGOTADO"
    if producto.stock_actual <= producto.stock_minimo:
        return "STOCK BAJO"
    return "ÓPTIMO"


def _pdf_tabla_reporte(
    titulo: str,
    subtitulo: str,
    columnas: Sequence[str],
    filas: Sequence[Sequence[str]],
    filepath: str,
    pesos: Sequence[float] | None = None,
    alineaciones: Sequence[str] | None = None,
) -> str:
    """Genera un PDF apaisado genérico con título, resumen y tabla."""
    doc = SimpleDocTemplate(
        filepath,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
    )

    estilos = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "GenTitle", parent=estilos["Normal"], fontName="Helvetica-Bold",
        fontSize=15, leading=18, textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "GenSubtitle", parent=estilos["Normal"], fontName="Helvetica",
        fontSize=8.5, leading=11, alignment=2, textColor=colors.HexColor("#475569"),
    )
    th_style = ParagraphStyle(
        "GenTH", parent=estilos["Normal"], fontName="Helvetica-Bold",
        fontSize=8.5, leading=10, textColor=colors.white, alignment=1,
    )
    td_style = ParagraphStyle(
        "GenTD", parent=estilos["Normal"], fontName="Helvetica",
        fontSize=8, leading=10, textColor=colors.HexColor("#1e293b"),
    )
    td_center = ParagraphStyle("GenTDCenter", parent=td_style, alignment=1)
    td_right = ParagraphStyle("GenTDRight", parent=td_style, alignment=2)

    generado = datetime.now()
    elements = []

    hdr_data = [[
        Paragraph(
            f"<b>{_texto_pdf(APP_NAME)}</b><br/>"
            f"<font size=11 color='#0284c7'>{_texto_pdf(titulo)}</font>",
            title_style,
        ),
        Paragraph(
            f"<b>Generado:</b> {generado.strftime('%d/%m/%Y %H:%M')}<br/>"
            f"{_texto_pdf(subtitulo)}",
            subtitle_style,
        ),
    ]]
    t_hdr = Table(hdr_data, colWidths=[170 * mm, 103 * mm])
    t_hdr.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_hdr)
    elements.append(Spacer(1, 4 * mm))

    usable = 273 * mm
    pesos = list(pesos or [1] * len(columnas))
    if len(pesos) != len(columnas):
        pesos = [1] * len(columnas)
    total_pesos = sum(pesos) or len(columnas)
    widths = [usable * p / total_pesos for p in pesos]

    alineaciones = list(alineaciones or ["L"] * len(columnas))
    if len(alineaciones) != len(columnas):
        alineaciones = ["L"] * len(columnas)

    table_rows = [[Paragraph(f"<b>{_texto_pdf(c)}</b>", th_style) for c in columnas]]
    for fila in filas:
        row = []
        for i, valor in enumerate(fila[:len(columnas)]):
            estilo = td_center if alineaciones[i] == "C" else (
                td_right if alineaciones[i] == "R" else td_style
            )
            row.append(Paragraph(_texto_pdf(valor), estilo))
        while len(row) < len(columnas):
            row.append(Paragraph("", td_style))
        table_rows.append(row)

    if not filas:
        table_rows.append([
            Paragraph("No hay datos para el reporte seleccionado.", td_style),
            *["" for _ in range(len(columnas) - 1)],
        ])

    tabla = Table(table_rows, colWidths=widths, repeatRows=1)
    estilo_tabla = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -2), 0.3, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if not filas:
        estilo_tabla.append(("SPAN", (0, -1), (-1, -1)))
        estilo_tabla.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f8fafc")))
    else:
        for r in range(1, len(table_rows)):
            if r % 2 == 0:
                estilo_tabla.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f8fafc")))

    tabla.setStyle(TableStyle(estilo_tabla))
    elements.append(tabla)

    doc.build(elements, canvasmaker=NumberedCanvas)
    return filepath


def _excel_tabla_reporte(
    titulo: str,
    subtitulo: str,
    columnas: Sequence[str],
    filas: Sequence[Sequence[str]],
    filepath: str,
    sheet_name: str,
    alineaciones: Sequence[str] | None = None,
    anchos: Sequence[float] | None = None,
) -> str:
    """Genera un Excel genérico con título, resumen, encabezados y tabla."""
    if not HAS_OPENPYXL:
        if not filepath.lower().endswith(".csv"):
            filepath = str(Path(filepath).with_suffix(".csv"))
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([f"{APP_NAME} - {titulo}"])
            writer.writerow([subtitulo])
            writer.writerow([])
            writer.writerow(list(columnas))
            writer.writerows(filas)
        return filepath

    generado = datetime.now()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = (sheet_name or "Reporte")[:31]
    ws.views.sheetView[0].showGridLines = True

    n_cols = max(1, len(columnas))
    last_col = get_column_letter(n_cols)

    font_title = Font(name="Calibri", size=16, bold=True, color="0F172A")
    font_subtitle = Font(name="Calibri", size=10, italic=True, color="475569")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_data = Font(name="Calibri", size=10, color="0F172A")

    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    thin_side = Side(border_style="thin", color="CBD5E1")
    border_cell = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    ws.merge_cells(f"A1:{last_col}1")
    ws["A1"] = f"{APP_NAME} – {titulo}"
    ws["A1"].font = font_title
    ws["A1"].alignment = Alignment(vertical="center")

    ws.merge_cells(f"A2:{last_col}2")
    ws["A2"] = f"Generado: {generado.strftime('%d/%m/%Y %H:%M')}  |  {subtitulo}"
    ws["A2"].font = font_subtitle
    ws["A2"].alignment = Alignment(vertical="center")

    header_row = 4
    for col_idx, nombre in enumerate(columnas, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=nombre)
        cell.font = font_header
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border_cell
    ws.row_dimensions[header_row].height = 30

    alineaciones = list(alineaciones or ["L"] * n_cols)
    if len(alineaciones) != n_cols:
        alineaciones = ["L"] * n_cols

    row_idx = header_row
    for fila in filas:
        row_idx += 1
        ws.row_dimensions[row_idx].height = 20
        for col_idx, valor in enumerate(fila[:n_cols], start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=valor)
            cell.font = font_data
            cell.border = border_cell
            if row_idx % 2 == 0:
                cell.fill = zebra_fill
            al = alineaciones[col_idx - 1]
            cell.alignment = Alignment(
                horizontal="right" if al == "R" else ("center" if al == "C" else "left"),
                vertical="center",
            )

    if filas:
        ws.auto_filter.ref = f"A{header_row}:{last_col}{row_idx}"
    else:
        row_idx += 1
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=n_cols)
        vacio = ws.cell(
            row=row_idx, column=1,
            value="No hay datos para el reporte seleccionado.",
        )
        vacio.font = Font(name="Calibri", size=11, italic=True, color="64748B")
        vacio.alignment = Alignment(horizontal="center", vertical="center")

    ws.freeze_panes = f"A{header_row + 1}"

    if anchos and len(anchos) == n_cols:
        for i, ancho in enumerate(anchos, start=1):
            ws.column_dimensions[get_column_letter(i)].width = ancho
    else:
        for i in range(1, n_cols + 1):
            max_len = len(str(columnas[i - 1]))
            for fila in filas:
                if i - 1 < len(fila):
                    max_len = max(max_len, len(str(fila[i - 1])))
            ws.column_dimensions[get_column_letter(i)].width = max(12, min(max_len + 3, 45))

    wb.save(filepath)
    return filepath


def _datos_inventario(productos: Sequence[Producto]):
    columnas = [
        "Código", "Producto", "Categoría", "Unidad", "Stock", "Mínimo",
        f"Costo ({CURRENCY})", f"Venta ({CURRENCY})", f"Gan. Unit. ({CURRENCY})",
        "Margen %", f"Gan. Total ({CURRENCY})", "Estado",
    ]
    filas = []
    total_costo = Decimal("0.00")
    total_venta = Decimal("0.00")
    total_ganancia = Decimal("0.00")

    for p in productos:
        pc = p.precio_compra_bs
        pv = p.precio_venta_bs
        ganancia_u = pv - pc
        margen = (ganancia_u / pc * 100) if pc > 0 else Decimal("0.0")
        ganancia_tot = (p.stock_actual * ganancia_u) if p.stock_actual > 0 else Decimal("0.00")
        if p.stock_actual > 0:
            total_costo += p.stock_actual * pc
            total_venta += p.stock_actual * pv
            total_ganancia += ganancia_tot

        filas.append([
            p.codigo_barras,
            p.descripcion,
            p.categoria.nombre if p.categoria else "-",
            p.unidad_medida,
            _cantidad_texto(p.stock_actual),
            _cantidad_texto(p.stock_minimo),
            _num(pc),
            _num(pv),
            _num(ganancia_u),
            f"{margen:.1f}%",
            _num(ganancia_tot),
            _estado_stock_texto(p),
        ])

    subtitulo = (
        f"Productos activos: {len(productos)}  |  "
        f"Inversión: {CURRENCY} {_num(total_costo)}  |  "
        f"Valor de venta: {CURRENCY} {_num(total_venta)}  |  "
        f"Ganancia potencial: {CURRENCY} {_num(total_ganancia)}"
    )
    return columnas, filas, subtitulo


def exportar_inventario_excel(productos: Sequence[Producto], filepath: str) -> str:
    columnas, filas, subtitulo = _datos_inventario(productos)
    return _excel_tabla_reporte(
        "REPORTE DE INVENTARIO", subtitulo, columnas, filas, filepath, "Inventario",
        alineaciones=["C", "L", "L", "C", "R", "R", "R", "R", "R", "R", "R", "C"],
        anchos=[13, 38, 18, 9, 12, 12, 13, 13, 15, 10, 15, 14],
    )


def exportar_inventario_pdf(productos: Sequence[Producto], filepath: str) -> str:
    columnas, filas, subtitulo = _datos_inventario(productos)
    return _pdf_tabla_reporte(
        "REPORTE DE INVENTARIO", subtitulo, columnas, filas, filepath,
        pesos=[1.1, 3.4, 1.5, 0.8, 1.0, 1.0, 1.1, 1.1, 1.2, 0.9, 1.2, 1.2],
        alineaciones=["C", "L", "L", "C", "R", "R", "R", "R", "R", "R", "R", "C"],
    )


def _datos_ganancias(ranking: Sequence[dict]):
    columnas = [
        "Código", "Producto", "Cantidad Vendida",
        f"Ingresos ({CURRENCY})", f"Costo ({CURRENCY})",
        f"Ganancia Real ({CURRENCY})", "Margen %",
    ]
    filas = []
    total_ingresos = Decimal("0.00")
    total_costo = Decimal("0.00")
    total_ganancia = Decimal("0.00")

    for item in ranking:
        ingresos = Decimal(str(item.get("ingresos", 0) or 0))
        costo = Decimal(str(item.get("costo", 0) or 0))
        ganancia = Decimal(str(item.get("ganancia", ingresos - costo) or 0))
        margen = (ganancia / ingresos * 100) if ingresos > 0 else Decimal("0.0")
        total_ingresos += ingresos
        total_costo += costo
        total_ganancia += ganancia

        cant = Decimal(str(item.get("cantidad", 0) or 0))
        filas.append([
            item.get("codigo", "-") or "-",
            item.get("descripcion", "-") or "-",
            _cantidad_texto(cant),
            _num(ingresos),
            _num(costo),
            _num(ganancia),
            f"{margen:.1f}%",
        ])

    margen_total = (total_ganancia / total_ingresos * 100) if total_ingresos > 0 else Decimal("0.0")
    subtitulo = (
        f"Productos con ventas: {len(ranking)}  |  "
        f"Ingresos: {CURRENCY} {_num(total_ingresos)}  |  "
        f"Costo: {CURRENCY} {_num(total_costo)}  |  "
        f"Ganancia real: {CURRENCY} {_num(total_ganancia)}  |  "
        f"Margen: {margen_total:.1f}%"
    )
    return columnas, filas, subtitulo


def exportar_ganancias_excel(ranking: Sequence[dict], filepath: str) -> str:
    columnas, filas, subtitulo = _datos_ganancias(ranking)
    return _excel_tabla_reporte(
        "REPORTE DE GANANCIAS EN VENTAS", subtitulo, columnas, filas,
        filepath, "Ganancias",
        alineaciones=["C", "L", "R", "R", "R", "R", "R"],
        anchos=[14, 40, 16, 16, 16, 18, 11],
    )


def exportar_ganancias_pdf(ranking: Sequence[dict], filepath: str) -> str:
    columnas, filas, subtitulo = _datos_ganancias(ranking)
    return _pdf_tabla_reporte(
        "REPORTE DE GANANCIAS EN VENTAS", subtitulo, columnas, filas, filepath,
        pesos=[1.2, 4.0, 1.4, 1.5, 1.5, 1.7, 1.0],
        alineaciones=["C", "L", "R", "R", "R", "R", "R"],
    )


def _datos_ajustes(ajustes: Sequence) -> tuple[list[str], list[list[str]], str]:
    columnas = ["Fecha y Hora", "Producto", "Tipo", "Cantidad", "Motivo", "Usuario"]
    filas = []
    entradas = 0
    salidas = 0

    for a in ajustes:
        es_entrada = str(getattr(a, "tipo", "")).lower() == "entrada"
        if es_entrada:
            entradas += 1
        else:
            salidas += 1
        filas.append([
            a.fecha.strftime("%d/%m/%Y %H:%M") if getattr(a, "fecha", None) else "-",
            a.producto.descripcion if getattr(a, "producto", None) else "(Producto eliminado)",
            "ENTRADA" if es_entrada else "SALIDA",
            f"{'+' if es_entrada else '-'}{_cantidad_texto(a.cantidad)}",
            a.motivo or "-",
            a.usuario.username if getattr(a, "usuario", None) else "-",
        ])

    subtitulo = (
        f"Ajustes registrados: {len(ajustes)}  |  "
        f"Entradas: {entradas}  |  Salidas: {salidas}"
    )
    return columnas, filas, subtitulo


def exportar_ajustes_excel(ajustes: Sequence, filepath: str) -> str:
    columnas, filas, subtitulo = _datos_ajustes(ajustes)
    return _excel_tabla_reporte(
        "REPORTE DE HISTORIAL DE AJUSTES", subtitulo, columnas, filas,
        filepath, "Ajustes",
        alineaciones=["C", "L", "C", "R", "L", "C"],
        anchos=[18, 40, 12, 12, 42, 18],
    )


def exportar_ajustes_pdf(ajustes: Sequence, filepath: str) -> str:
    columnas, filas, subtitulo = _datos_ajustes(ajustes)
    return _pdf_tabla_reporte(
        "REPORTE DE HISTORIAL DE AJUSTES", subtitulo, columnas, filas, filepath,
        pesos=[1.6, 4.0, 1.1, 1.0, 4.2, 1.6],
        alineaciones=["C", "L", "C", "R", "L", "C"],
    )
