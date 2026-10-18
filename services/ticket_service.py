"""
services/ticket_service.py – Generación de tickets de venta en PDF con ReportLab.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from config import APP_NAME, CURRENCY
from models.venta import Venta


# Ancho de papel térmico 80 mm
THERMAL_WIDTH  = 80 * mm
THERMAL_HEIGHT = 297 * mm   # altura larga; ReportLab recorta en impresión


def generar_ticket_pdf(venta: Venta, destino: Path | None = None) -> Path:
    """
    Genera un PDF tipo ticket (80 mm de ancho) para la venta indicada.

    :param venta:    Objeto Venta con detalles cargados.
    :param destino:  Ruta del archivo PDF. Si None, se genera en directorio temporal.
    :returns:        Ruta del PDF generado.
    """
    if destino is None:
        tickets_dir = Path("tickets")
        tickets_dir.mkdir(parents=True, exist_ok=True)
        destino = tickets_dir / f"ticket_{venta.numero_transaccion}.pdf"

    # Calcular altura real del ticket
    lineas = 14 + len(venta.detalles) * 2
    altura = lineas * 5 * mm + 40 * mm

    c = canvas.Canvas(str(destino), pagesize=(THERMAL_WIDTH, altura))

    y = altura - 8 * mm
    ancho = THERMAL_WIDTH - 4 * mm
    cx = THERMAL_WIDTH / 2

    def nl(pasos=1):
        nonlocal y
        y -= pasos * 5 * mm

    # ── Encabezado ───────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(cx, y, APP_NAME)
    nl()
    c.setFont("Helvetica", 7)
    c.drawCentredString(cx, y, f"Ticket #{venta.numero_transaccion}")
    nl()
    c.drawCentredString(cx, y, datetime.now().strftime("%d/%m/%Y %H:%M"))
    nl()

    # Cajero
    cajero = venta.usuario.username if venta.usuario else "-"
    c.drawString(2 * mm, y, f"Cajero: {cajero}")
    nl()

    # Cliente
    if venta.cliente:
        c.drawString(2 * mm, y, f"Cliente: {venta.cliente.razon_social}")
        nl()
        c.drawString(2 * mm, y, f"NIT: {venta.cliente.nit}")
        nl()

    # Método de pago
    if venta.metodo_pago == "mixto":
        c.drawString(2 * mm, y, "Pago: Mixto (QR + Efectivo)")
        nl()
        if venta.observacion:
            c.setFont("Helvetica", 6)
            c.drawString(4 * mm, y, venta.observacion[:40])
            nl()
            c.setFont("Helvetica", 7)
    elif venta.metodo_pago in ("QR", "qr"):
        c.drawString(2 * mm, y, "Pago: QR (Confirmado)")
        nl()
        if getattr(venta, "referencia_pago", None):
            c.setFont("Helvetica", 6)
            c.drawString(4 * mm, y, f"Ref: {venta.referencia_pago[:35]}")
            nl()
            c.setFont("Helvetica", 7)
    else:
        c.drawString(2 * mm, y, f"Pago: {venta.metodo_pago.capitalize()}")
        nl()

    # ── Separador ────────────────────────────────────────────────────────────
    c.setLineWidth(0.3)
    c.line(2 * mm, y, ancho, y)
    nl(0.5)

    # ── Encabezado de columnas ───────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 7)
    c.drawString(2 * mm, y, "Producto")
    c.drawRightString(ancho, y, f"Subtotal {CURRENCY}")
    nl()
    c.line(2 * mm, y, ancho, y)
    nl(0.5)

    # ── Ítems ────────────────────────────────────────────────────────────────
    c.setFont("Helvetica", 7)
    for det in venta.detalles:
        nombre = det.producto.descripcion[:28] if det.producto else "---"
        c.drawString(2 * mm, y, nombre)
        c.drawRightString(ancho, y, f"{det.subtotal_bs:.2f}")
        nl()
        c.drawString(4 * mm, y, f"  {det.cantidad} {det.producto.unidad_medida} x {det.precio_unitario_bs:.2f}")
        nl()

    # ── Total ────────────────────────────────────────────────────────────────
    c.line(2 * mm, y, ancho, y)
    nl(0.5)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(2 * mm, y, "TOTAL:")
    c.drawRightString(ancho, y, f"{CURRENCY} {venta.total_bs:.2f}")
    nl(2)

    c.setFont("Helvetica", 6)
    c.drawCentredString(cx, y, "Gracias por su compra")

    c.save()
    return destino


def respaldar_base_de_datos(db_path: Path, destino_dir: Path | None = None) -> Path:
    """
    Copia el archivo .db con fecha en el nombre.

    :param db_path:     Ruta del archivo minimarket.db.
    :param destino_dir: Carpeta destino. Si None, usa la misma carpeta que db_path.
    :returns:           Ruta del archivo de respaldo creado.
    """
    import shutil

    if destino_dir is None:
        destino_dir = db_path.parent

    destino_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = destino_dir / f"minimarket_backup_{stamp}.db"
    shutil.copy2(str(db_path), str(destino))
    return destino
