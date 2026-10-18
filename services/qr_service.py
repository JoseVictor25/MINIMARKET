"""
services/qr_service.py – Generación de Códigos QR Dinámicos con Monto y Estándar EMVCo / Simple QR.
"""
from __future__ import annotations

import io
import time
from decimal import Decimal
from pathlib import Path

try:
    import qrcode
except ImportError:
    qrcode = None

from PIL import Image, ImageDraw, ImageFont
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage

from config import QR_DIR


def crc16_ccitt(data: str) -> str:
    """Calcula el checksum CRC16-CCITT (estándar EMVCo / QR Simple)."""
    crc = 0xFFFF
    for ch in data.encode("utf-8"):
        crc = ((crc >> 8) | (crc << 8)) & 0xFFFF
        crc ^= ch
        crc ^= (crc & 0xFF) >> 4
        crc ^= (crc << 12) & 0xFFFF
        crc ^= ((crc & 0xFF) << 5) & 0xFFFF
    return f"{crc:04X}"


def construir_emvco_payload(
    monto: Decimal,
    nombre_comercio: str = "MINI MARKET",
    ciudad: str = "LA PAZ",
    referencia: str = "",
) -> str:
    """
    Construye la cadena TLV de estándar EMVCo Merchant-Presented para Bolivia (QR Simple).
    Incluye el tag 54 con el monto exacto y el tag 53 con la moneda BOB (068).
    """
    m_str = f"{monto:.2f}"
    ref = referencia or f"TRX{int(time.time()) % 1000000:06d}"
    nom = (nombre_comercio[:20] if nombre_comercio else "MINI MARKET").upper()
    ciu = (ciudad[:15] if ciudad else "LA PAZ").upper()

    # Formato e iniciación dinámica
    payload = "000201010212"

    # Tag 26: Cuenta / Identificador Merchant
    cuenta = "0010BO.COM.ACH.SIMPLE0112100000000000"
    payload += f"26{len(cuenta):02d}{cuenta}"

    # Tag 52: Categoría
    payload += "52040000"

    # Tag 53: Moneda BOB (068 = Bolivianos)
    payload += "5303068"

    # Tag 54: Monto exacto de la transacción
    payload += f"54{len(m_str):02d}{m_str}"

    # Tag 58: País (BO)
    payload += "5802BO"

    # Tag 59: Nombre del Comercio
    payload += f"59{len(nom):02d}{nom}"

    # Tag 60: Ciudad
    payload += f"60{len(ciu):02d}{ciu}"

    # Tag 62: Datos adicionales (Referencia)
    add_data = f"01{len(ref):02d}{ref}"
    payload += f"62{len(add_data):02d}{add_data}"

    # Tag 63: CRC16
    payload += "6304"
    crc = crc16_ccitt(payload)
    return payload + crc


def generar_qr_pil(
    monto: Decimal,
    nombre_comercio: str = "MINI MARKET",
    referencia: str = "",
    tamano: int = 340,
) -> Image.Image:
    """Genera una imagen PIL del código QR con el monto embebido."""
    if qrcode is None:
        img = Image.new("RGB", (tamano, tamano), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((tamano // 4, tamano // 2 - 20), f"QR: Bs {monto:.2f}\n(Falta qrcode)", fill="#0f172a")
        return img

    payload = construir_emvco_payload(monto, nombre_comercio=nombre_comercio, referencia=referencia)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    img = img.resize((tamano, tamano), Image.Resampling.LANCZOS)
    return img


def generar_pixmap_qr_dinamico(
    monto: Decimal,
    nombre_comercio: str = "MINI MARKET",
    referencia: str = "",
    tamano: int = 328,
) -> QPixmap:
    """Genera un QPixmap directamente para ser mostrado en PyQt5."""
    img = generar_qr_pil(monto, nombre_comercio, referencia, tamano=tamano)

    # Convertir PIL Image a QPixmap en memoria
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    return pixmap
