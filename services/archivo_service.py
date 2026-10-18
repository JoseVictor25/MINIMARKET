"""
services/archivo_service.py – Gestión y almacenamiento de archivos e imágenes del sistema.

Permite:
  - Guardar y actualizar imágenes QR por cajero/usuario.
  - Guardar comprobantes de pago adjuntos en transacciones QR.
  - Resolver rutas relativas o absolutas de forma segura y portable.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from config import BASE_DIR, QR_DIR, COMPROBANTES_DIR


EXTENSIONES_PERMITIDAS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def resolver_ruta(ruta: str | Path | None) -> Path | None:
    """
    Resuelve una ruta de archivo tanto si es relativa a BASE_DIR como si es absoluta.
    Retorna Path si el archivo existe físicamente, o None en caso contrario.
    """
    if not ruta:
        return None
    p = Path(ruta)
    if p.is_absolute() and p.exists():
        return p
    rel = BASE_DIR / ruta
    if rel.exists():
        return rel
    return None


def guardar_qr_usuario(usuario_id: int, ruta_origen: str | Path) -> str:
    """
    Copia y registra una imagen QR para un usuario/cajero específico.

    :param usuario_id:   ID del usuario / cajero.
    :param ruta_origen:  Ruta al archivo de imagen seleccionado por el usuario.
    :returns:            Ruta relativa normalizada para almacenar en la BD (ej. 'qrs/cajero_1_...png').
    :raises ValueError:  Si el archivo no existe o no tiene una extensión de imagen válida.
    """
    origen = Path(ruta_origen)
    if not origen.exists() or not origen.is_file():
        raise ValueError(f"El archivo '{ruta_origen}' no existe.")

    suffix = origen.suffix.lower()
    if suffix not in EXTENSIONES_PERMITIDAS:
        raise ValueError(
            f"Formato no permitido ({suffix}). Use: {', '.join(sorted(EXTENSIONES_PERMITIDAS))}"
        )

    QR_DIR.mkdir(parents=True, exist_ok=True)

    # Limpiar QRs previos del mismo usuario para no acumular archivos huérfanos
    for previo in QR_DIR.glob(f"cajero_{usuario_id}_*"):
        try:
            previo.unlink(missing_ok=True)
        except Exception:
            pass

    nombre_destino = f"cajero_{usuario_id}_{int(time.time())}{suffix}"
    destino = QR_DIR / nombre_destino
    shutil.copy2(origen, destino)

    return f"qrs/{nombre_destino}"


def eliminar_qr_usuario(ruta_qr: str | Path | None) -> bool:
    """Elimina físicamente el archivo QR si existe en disco."""
    p = resolver_ruta(ruta_qr)
    if p and p.exists():
        try:
            p.unlink(missing_ok=True)
            return True
        except Exception:
            return False
    return False


def guardar_comprobante_pago(ruta_origen: str | Path, prefijo: str = "pago") -> str:
    """
    Copia una imagen de comprobante o captura de pago a la carpeta comprobantes/.

    :param ruta_origen:  Ruta del comprobante seleccionado.
    :param prefijo:      Identificador opcional (ej: número de transacción).
    :returns:            Ruta relativa guardada (ej. 'comprobantes/pago_...jpg').
    """
    origen = Path(ruta_origen)
    if not origen.exists() or not origen.is_file():
        raise ValueError(f"El archivo '{ruta_origen}' no existe.")

    suffix = origen.suffix.lower()
    if suffix not in EXTENSIONES_PERMITIDAS:
        raise ValueError(f"Formato de imagen inválido: {suffix}")

    COMPROBANTES_DIR.mkdir(parents=True, exist_ok=True)

    nombre_destino = f"comprobante_{prefijo}_{int(time.time())}{suffix}"
    destino = COMPROBANTES_DIR / nombre_destino
    shutil.copy2(origen, destino)

    return f"comprobantes/{nombre_destino}"
