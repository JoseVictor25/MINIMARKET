"""
services/print_service.py – Impresión directa de tickets con QPrinter.

Permite imprimir el mismo layout que se usa para el PDF, con tamaño de página
personalizado (80 mm de ancho por la altura exacta del contenido). Así se evita
el sobrante de papel de los tickets.
"""
from __future__ import annotations

from reportlab.lib.units import mm

from services.ticket_service import TicketLayout


def imprimir_layout(layout: TicketLayout, parent=None, ancho_mm: float = 80.0) -> bool:
    """
    Abre el diálogo de impresión y envía el layout a la impresora elegida.

    :returns: True si se aceptó el diálogo y se dibujó; False si se canceló.
    """
    from PyQt5.QtCore import QMarginsF, QSizeF
    from PyQt5.QtGui import QPageLayout, QPageSize, QPainter
    from PyQt5.QtPrintSupport import QPrintDialog, QPrinter
    from PyQt5.QtWidgets import QMessageBox

    altura_mm = layout.altura() / mm

    printer = QPrinter(QPrinter.HighResolution)
    try:
        printer.setResolution(203)  # resolución típica de impresoras térmicas
    except Exception:
        pass

    page_size = QPageSize(
        QSizeF(ancho_mm, altura_mm),
        QPageSize.Millimeter,
        "Ticket 80mm",
        QPageSize.ExactMatch,
    )
    printer.setPageSize(page_size)
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)
    printer.setFullPage(True)

    dlg = QPrintDialog(printer, parent)
    dlg.setWindowTitle("Imprimir ticket")
    if dlg.exec_() != QPrintDialog.Accepted:
        return False

    painter = QPainter(printer)
    try:
        dpi = printer.resolution() or 203
        escala = dpi / 25.4  # 1 unidad del painter = 1 mm
        painter.scale(escala, escala)
        layout.dibujar_qt(painter, escala)
    except Exception as e:
        QMessageBox.critical(parent, "Error de impresión", f"No se pudo imprimir el ticket:\n{e}")
        return False
    finally:
        painter.end()
    return True
