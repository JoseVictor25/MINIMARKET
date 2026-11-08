"""
services/ticket_service.py – Generación de tickets de venta en PDF con ReportLab.

Los tickets se construyen con un layout de líneas que calcula la altura exacta
del contenido. De esta forma el PDF ocupa únicamente el papel necesario y no
deja sobrantes arriba ni abajo.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from config import APP_NAME, CURRENCY
from models.venta import Venta


# Ancho de papel térmico 80 mm. El área imprimible real suele ser 72 mm.
THERMAL_WIDTH = 80 * mm
LINE_HEIGHT = 4.6 * mm
TOP_MARGIN = 5 * mm
BOTTOM_MARGIN = 4 * mm
SAFE_MARGIN = 2 * mm


def wrap_text(texto, font: str = "Helvetica", size: float = 7,
              max_width: float = 72 * mm) -> list[str]:
    """Divide un texto en líneas que caben en ``max_width`` puntos."""
    texto = str(texto or "").strip()
    if not texto:
        return [""]

    palabras = texto.split()
    lineas: list[str] = []
    actual = ""
    for palabra in palabras:
        prueba = f"{actual} {palabra}".strip()
        if not actual or stringWidth(prueba, font, size) <= max_width:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas or [""]


class TicketLayout:
    """
    Layout simple para tickets térmicos.

    Guarda operaciones de dibujo y calcula la altura exacta antes de crear el
    PDF. También puede dibujarse sobre un ``QPainter`` para impresión directa.
    """

    def __init__(self, width: float = THERMAL_WIDTH):
        self.width = width
        self.ops: list[dict] = []

    # ── Construcción ────────────────────────────────────────────────────────
    def text(self, texto, font: str = "Helvetica", size: float = 7,
             x: float | None = None, align: str = "left",
             max_width: float | None = None):
        lineas = wrap_text(texto, font, size, max_width) if max_width else [str(texto)]
        self.ops.append({
            "tipo": "texto", "lineas": lineas, "font": font,
            "size": size, "x": x, "align": align,
        })

    def fila(self, label, value, font: str = "Helvetica", size: float = 7,
             x: float | None = None, x_right: float | None = None,
             max_width_label: float | None = None):
        lineas = wrap_text(label, font, size, max_width_label) if max_width_label else [str(label)]
        self.ops.append({
            "tipo": "fila", "lineas": lineas, "value": str(value),
            "font": font, "size": size, "x": x, "x_right": x_right,
        })

    def line(self, x1: float | None = None, x2: float | None = None,
             gap: float = 1.5 * mm, width: float = 0.3):
        self.ops.append({
            "tipo": "linea", "x1": x1, "x2": x2,
            "gap": gap, "width": width,
        })

    def firmas(self):
        self.ops.append({"tipo": "firmas"})

    def gap(self, n: float = 1):
        self.ops.append({"tipo": "gap", "n": n})

    # ── Medición y dibujo ───────────────────────────────────────────────────
    def altura(self) -> float:
        total = TOP_MARGIN + BOTTOM_MARGIN
        for op in self.ops:
            if op["tipo"] in ("texto", "fila"):
                total += LINE_HEIGHT * len(op["lineas"])
            elif op["tipo"] == "linea":
                total += op["gap"]
            elif op["tipo"] == "firmas":
                total += LINE_HEIGHT * 2
            elif op["tipo"] == "gap":
                total += LINE_HEIGHT * op["n"]
        return max(total, 60 * mm)

    def _x_izq(self, x):
        return x if x is not None else SAFE_MARGIN

    def _x_der(self, x):
        return x if x is not None else self.width - SAFE_MARGIN

    def dibujar(self, c: canvas.Canvas):
        y = self.altura() - TOP_MARGIN
        for op in self.ops:
            if op["tipo"] == "texto":
                c.setFont(op["font"], op["size"])
                for linea in op["lineas"]:
                    if op["align"] == "center":
                        c.drawCentredString(op["x"] if op["x"] is not None else self.width / 2, y, linea)
                    elif op["align"] == "right":
                        c.drawRightString(self._x_der(op["x"]), y, linea)
                    else:
                        c.drawString(self._x_izq(op["x"]), y, linea)
                    y -= LINE_HEIGHT
            elif op["tipo"] == "fila":
                c.setFont(op["font"], op["size"])
                for i, linea in enumerate(op["lineas"]):
                    c.drawString(self._x_izq(op["x"]), y, linea)
                    if i == 0:
                        c.drawRightString(self._x_der(op["x_right"]), y, op["value"])
                    y -= LINE_HEIGHT
            elif op["tipo"] == "linea":
                c.setLineWidth(op["width"])
                # La línea se centra entre la línea base del texto anterior y
                # la del siguiente, en lugar de dibujarse pegada al texto que
                # viene debajo.
                y_linea = y + (LINE_HEIGHT - op["gap"]) / 2
                c.line(
                    op["x1"] if op["x1"] is not None else SAFE_MARGIN, y_linea,
                    op["x2"] if op["x2"] is not None else self.width - SAFE_MARGIN, y_linea,
                )
                y -= op["gap"]
            elif op["tipo"] == "firmas":
                c.setLineWidth(0.3)
                c.line(8 * mm, y, 36 * mm, y)
                c.line(44 * mm, y, 72 * mm, y)
                y -= LINE_HEIGHT
                c.setFont("Helvetica", 7)
                c.drawCentredString(22 * mm, y, "Firma Cajero")
                c.drawCentredString(58 * mm, y, "Firma Supervisor")
                y -= LINE_HEIGHT
            elif op["tipo"] == "gap":
                y -= LINE_HEIGHT * op["n"]

    def dibujar_qt(self, painter, dpi: float = 203.0):
        """
        Dibuja el layout sobre un ``QPainter`` sin transformar.

        El layout guarda posiciones y tamaños en puntos PostScript (1/72"),
        por lo que se convierten a píxeles del dispositivo usando ``dpi``.
        Así el texto conserva su tamaño físico real al imprimir.

        :param painter: QPainter activo.
        :param dpi:     resolución del dispositivo de salida.
        """
        from PyQt5.QtCore import QPointF, Qt
        from PyQt5.QtGui import QFont, QFontMetricsF, QPen

        dpi = float(dpi or 203.0)
        px_por_pt = dpi / 72.0

        def px(valor_pt: float) -> float:
            return float(valor_pt) * px_por_pt

        ancho = px(self.width)
        y = px(self.altura() - TOP_MARGIN)

        def preparar_fuente(nombre: str, tam: float) -> QFontMetricsF:
            f = QFont("Arial")
            # setPixelSize evita que Qt aplique el DPI lógico de la pantalla.
            f.setPixelSize(max(1, int(round(tam * px_por_pt))))
            f.setBold("Bold" in nombre)
            painter.setFont(f)
            device = painter.device()
            return QFontMetricsF(f, device) if device is not None else QFontMetricsF(f)

        for op in self.ops:
            if op["tipo"] == "texto":
                fm = preparar_fuente(op["font"], op["size"])
                for linea in op["lineas"]:
                    w = fm.horizontalAdvance(linea)
                    if op["align"] == "center":
                        x = (ancho - w) / 2
                    elif op["align"] == "right":
                        x = ancho - px(SAFE_MARGIN) - w
                    else:
                        x = px(op["x"] if op["x"] is not None else SAFE_MARGIN)
                    painter.drawText(QPointF(x, y), linea)
                    y -= px(LINE_HEIGHT)
            elif op["tipo"] == "fila":
                fm = preparar_fuente(op["font"], op["size"])
                for i, linea in enumerate(op["lineas"]):
                    x = px(op["x"] if op["x"] is not None else SAFE_MARGIN)
                    painter.drawText(QPointF(x, y), linea)
                    if i == 0:
                        w = fm.horizontalAdvance(op["value"])
                        xr = px(op["x_right"] if op["x_right"] is not None else self.width - SAFE_MARGIN) - w
                        painter.drawText(QPointF(xr, y), op["value"])
                    y -= px(LINE_HEIGHT)
            elif op["tipo"] == "linea":
                painter.setPen(QPen(Qt.black, max(0.8, px(op["width"]))))
                x1 = px(op["x1"] if op["x1"] is not None else SAFE_MARGIN)
                x2 = px(op["x2"] if op["x2"] is not None else self.width - SAFE_MARGIN)
                y_linea = y + (px(LINE_HEIGHT) - px(op["gap"])) / 2
                painter.drawLine(QPointF(x1, y_linea), QPointF(x2, y_linea))
                y -= px(op["gap"])
            elif op["tipo"] == "firmas":
                painter.setPen(QPen(Qt.black, max(0.8, px(0.3))))
                painter.drawLine(QPointF(px(8 * mm), y), QPointF(px(36 * mm), y))
                painter.drawLine(QPointF(px(44 * mm), y), QPointF(px(72 * mm), y))
                y -= px(LINE_HEIGHT)
                fm = preparar_fuente("Helvetica", 7)
                for texto, centro in (("Firma Cajero", 22), ("Firma Supervisor", 58)):
                    w = fm.horizontalAdvance(texto)
                    painter.drawText(QPointF(px(centro * mm) - w / 2, y), texto)
                y -= px(LINE_HEIGHT)
            elif op["tipo"] == "gap":
                y -= px(LINE_HEIGHT * op["n"])


# ══════════════════════════════════════════════════════════════════════════════
#  TICKET DE VENTA
# ══════════════════════════════════════════════════════════════════════════════

def construir_layout_ticket(venta: Venta) -> TicketLayout:
    """Construye el layout del ticket de venta (sin generar todavía el PDF)."""
    layout = TicketLayout()

    # Encabezado
    layout.text(APP_NAME, "Helvetica-Bold", 9, align="center")
    layout.text(f"Ticket #{venta.numero_transaccion}", "Helvetica", 7, align="center")
    layout.text(datetime.now().strftime("%d/%m/%Y %H:%M"), "Helvetica", 7, align="center")

    # Cajero y cliente
    cajero = venta.usuario.username if venta.usuario else "-"
    layout.text(f"Cajero: {cajero}", "Helvetica", 7)
    if venta.cliente:
        layout.text(
            f"Cliente: {venta.cliente.razon_social}",
            "Helvetica", 7, max_width=THERMAL_WIDTH - 2 * SAFE_MARGIN,
        )
        layout.text(f"NIT: {venta.cliente.nit}", "Helvetica", 7)

    # Método de pago
    if venta.metodo_pago == "mixto":
        layout.text("Pago: Mixto (QR + Efectivo)", "Helvetica", 7)
        if venta.observacion:
            layout.text(
                venta.observacion, "Helvetica", 6, x=4 * mm,
                max_width=THERMAL_WIDTH - 6 * mm,
            )
    elif venta.metodo_pago in ("QR", "qr"):
        layout.text("Pago: QR (Confirmado)", "Helvetica", 7)
        if getattr(venta, "referencia_pago", None):
            layout.text(
                f"Ref: {venta.referencia_pago}", "Helvetica", 6, x=4 * mm,
                max_width=THERMAL_WIDTH - 6 * mm,
            )
    else:
        layout.text(f"Pago: {venta.metodo_pago.capitalize()}", "Helvetica", 7)

    # Detalle
    layout.line()
    layout.fila("Producto", f"Subtotal {CURRENCY}", "Helvetica-Bold", 7)
    layout.line()

    for det in venta.detalles:
        nombre = det.producto.descripcion if det.producto else "---"
        layout.fila(
            nombre, f"{det.subtotal_bs:.2f}", "Helvetica", 7,
            max_width_label=THERMAL_WIDTH - 4 * mm - 22 * mm,
        )
        unidad = det.producto.unidad_medida if det.producto else ""
        layout.text(
            f"  {det.cantidad} {unidad} x {det.precio_unitario_bs:.2f}",
            "Helvetica", 7, x=4 * mm,
        )

    # Total y cierre
    layout.line()
    layout.fila("TOTAL:", f"{CURRENCY} {venta.total_bs:.2f}", "Helvetica-Bold", 9)
    layout.gap(1)
    layout.text("Gracias por su compra", "Helvetica", 6, align="center")
    return layout


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

    layout = construir_layout_ticket(venta)
    c = canvas.Canvas(str(destino), pagesize=(THERMAL_WIDTH, layout.altura()))
    layout.dibujar(c)
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
