"""
config.py – Configuración global del sistema Mini Market / POS.

Garantiza que la base de datos siempre se ubique junto al ejecutable,
tanto en desarrollo como en el paquete generado por PyInstaller.
Permite personalizar la identidad de marca (White-Label) para cada cliente.
"""
import sys
from pathlib import Path


def base_dir() -> Path:
    """
    Retorna la carpeta raíz del proyecto:
    - Empaquetado con PyInstaller → carpeta del .exe (sys.executable).
    - En desarrollo               → carpeta donde está este archivo.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


# ── Rutas del Sistema ────────────────────────────────────────────────────────
BASE_DIR: Path = base_dir()
DB_PATH:  Path = BASE_DIR / "minimarket.db"
QR_DIR:   Path = BASE_DIR / "qrs"
COMPROBANTES_DIR: Path = BASE_DIR / "comprobantes"

# Garantizar existencia de carpetas de almacenamiento
QR_DIR.mkdir(parents=True, exist_ok=True)
COMPROBANTES_DIR.mkdir(parents=True, exist_ok=True)


# ── Identidad de Marca por Cliente (White-Label) ──────────────────────────────
# Modifica estos valores para personalizar el sistema según el negocio del cliente:

APP_NAME         = "MT BALCERAS"               # Nombre comercial del negocio
APP_VERSION      = "1.0.0"                     # Versión del sistema
CURRENCY         = "Bs"                        # Símbolo de moneda (Bs, $, S/., etc.)

# Lema / Eslogan comercial (se muestra en el login debajo del logo si no está vacío)
# Ej: "CALIDAD • VARIEDAD • CONFIANZA" (deja "" para clientes sin lema)
SLOGAN           = "CALIDAD • PRECIO • SERVICIO"
SLOGAN_COLOR     = "#10b981"                   # Color del lema (ej. verde turquesa)

# Identidad visual de la marca
BRAND_COLOR      = "#f59e0b"                   # Color primario (ej: #bf1e61 Peke rosa, #f59e0b Balceras naranja)
BRAND_TEXT_COLOR = ""                          # Color del texto en botones ("" = automático según contraste)
LOGIN_BTN_TEXT   = "Ingresar al Sistema"       # Texto del botón principal de login
LOGIN_SUBTITLE   = "Ingrese sus credenciales para continuar" # Subtítulo del login


# ── Funciones auxiliares de color ─────────────────────────────────────────────
def get_brand_hover(hex_color: str = BRAND_COLOR) -> str:
    """Calcula automáticamente un tono más claro/brillante para el hover."""
    try:
        c = hex_color.lstrip('#')
        rgb = [int(c[i:i+2], 16) for i in (0, 2, 4)]
        new_rgb = [min(255, int(ch + (255 - ch) * 0.18)) for ch in rgb]
        return f"#{new_rgb[0]:02x}{new_rgb[1]:02x}{new_rgb[2]:02x}"
    except Exception:
        return hex_color


def get_brand_dark(hex_color: str = BRAND_COLOR) -> str:
    """Calcula automáticamente un tono más oscuro para el estado presionado."""
    try:
        c = hex_color.lstrip('#')
        rgb = [int(c[i:i+2], 16) for i in (0, 2, 4)]
        new_rgb = [max(0, int(ch * 0.82)) for ch in rgb]
        return f"#{new_rgb[0]:02x}{new_rgb[1]:02x}{new_rgb[2]:02x}"
    except Exception:
        return hex_color


def get_brand_text_color(hex_color: str = BRAND_COLOR, override: str = BRAND_TEXT_COLOR) -> str:
    """Retorna color de texto de alto contraste (#111827 para fondos claros, #ffffff para fondos oscuros)."""
    if override:
        return override
    try:
        c = hex_color.lstrip('#')
        r, g, b = [int(c[i:i+2], 16) for i in (0, 2, 4)]
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        return "#111827" if lum > 165 else "#ffffff"
    except Exception:
        return "#ffffff"


# ── Seguridad ────────────────────────────────────────────────────────────────
# Contraseña por defecto del primer usuario admin (cambiar tras primer inicio)
DEFAULT_ADMIN_PASSWORD = "admin123"
