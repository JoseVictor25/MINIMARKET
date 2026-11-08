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
    from PyQt5.QtCore import QSizeF
    from PyQt5.QtGui import QPageSize, QPainter
    from PyQt5.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo
    from PyQt5.QtWidgets import QMessageBox

    if not QPrinterInfo.availablePrinters():
        QMessageBox.warning(parent, "Impresora no disponible",
                            "No se encontró una impresora instalada. Conecte o configure una impresora e inténtelo de nuevo.")
        return False

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
    # PyQt5 usa la firma (left, top, right, bottom, unit). Pasar un QMarginsF
    # provoca "argument 1 has unexpected type 'QMarginsF'".
    printer.setPageMargins(0, 0, 0, 0, QPrinter.Millimeter)
    printer.setFullPage(True)

    dlg = QPrintDialog(printer, parent)
    dlg.setWindowTitle("Imprimir ticket")
    if dlg.exec_() != QPrintDialog.Accepted:
        return False

    painter = QPainter()
    if not painter.begin(printer):
        QMessageBox.warning(parent, "No se pudo imprimir",
                            "No se pudo iniciar la impresión. Revise que la impresora esté encendida, conectada y lista.")
        return False
    try:
        # Se dibuja directamente en unidades de dispositivo (píxeles) para
        # conservar el tamaño físico real del texto en la impresora.
        dpi = float(printer.resolution() or 203)
        layout.dibujar_qt(painter, dpi)
    except Exception:
        QMessageBox.critical(parent, "No se pudo imprimir",
                             "Ocurrió un problema al enviar el ticket. Revise la impresora e inténtelo de nuevo.")
        return False
    finally:
        painter.end()
    return True
