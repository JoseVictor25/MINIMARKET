"""
Servicio para consulta y reconocimiento automático de productos mediante código de barras.
Utiliza Open Food Facts, Open Products Facts y Open Beauty Facts como catálogos globales
para autocompletar descripción, marca y unidad de medida al pasar el escáner.
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import TypedDict


class DatosProductoOnline(TypedDict, total=False):
    descripcion: str
    marca: str
    cantidad: str
    categoria_texto: str
    unidad_medida: str


def normalizar_codigo_barras(codigo: str | None) -> str:
    """Elimina espacios y caracteres de control que puedan enviar los lectores ópticos."""
    if not codigo:
        return ""
    # Quitar retornos de carro, saltos de línea y espacios en blanco
    return re.sub(r"[\r\n\t\s]", "", str(codigo).strip())


def sugerir_unidad_medida(cantidad_str: str) -> str:
    """Deduce la unidad de medida (UN, KG, LT, ML, GR, etc.) a partir del texto de cantidad o empaque."""
    if not cantidad_str:
        return "UN"

    txt = cantidad_str.lower()
    if re.search(r"\b(ml|cl|cc)\b", txt):
        return "ML"
    if re.search(r"\b(l|lt|litro|litros)\b", txt):
        return "LT"
    if re.search(r"\b(kg|kilo|kilos|kilogramos)\b", txt):
        return "KG"
    if re.search(r"\b(g|gr|gramo|gramos)\b", txt):
        return "GR"
    if re.search(r"\b(m|mt|metro|metros)\b", txt):
        return "MT"
    if re.search(r"\b(pack|paquete|pq|caja|cj)\b", txt):
        return "PQ"

    return "UN"


def formatear_nombre_producto(nombre: str, marca: str, cantidad: str) -> str:
    """Construye un nombre de producto limpio y comercial sin redundancias."""
    cant_limpia = re.sub(r"\s*[eE]$", "", cantidad).strip()
    nom = nombre.strip()
    m = marca.strip()

    # Detectar si hay palabras compartidas entre nombre y marca para no repetir
    words_m = [w.lower() for w in re.findall(r"[a-zA-Z0-9]{3,}", m)]
    words_nom = [w.lower() for w in re.findall(r"[a-zA-Z0-9]{3,}", nom)]
    coincide = bool(set(words_m) & set(words_nom))

    if nom and not coincide and m:
        m_corta = m.split(",")[0].strip()
        base = f"{nom} ({m_corta})"
    elif nom:
        base = nom
    else:
        base = m

    if cant_limpia and cant_limpia.lower() not in base.lower():
        base = f"{base} {cant_limpia}"

    return re.sub(r"\s+", " ", base).strip()


def consultar_producto_online(codigo: str, timeout_segundos: float = 2.5) -> DatosProductoOnline | None:
    """
    Consulta las bases de datos abiertas para reconocer un producto por su código de barras.
    Prueba primero con Open Food Facts, y luego con Open Products Facts / Beauty Facts.
    Retorna un diccionario con descripción, marca y unidad de medida sugerida, o None si no se encuentra.
    """
    codigo_limpio = normalizar_codigo_barras(codigo)
    if not codigo_limpio or len(codigo_limpio) < 4:
        return None

    dominios = ["openfoodfacts.org", "openproductsfacts.org", "openbeautyfacts.org"]

    for dominio in dominios:
        url = f"https://world.{dominio}/api/v0/product/{codigo_limpio}.json"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "MiniMarketPOS-Bolivia/1.0 (pos.minimarket@gmail.com)",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_segundos) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == 1:
                    prod = data.get("product", {})

                    # Priorizar nombre en español o general
                    nombre = (
                        prod.get("product_name_es")
                        or prod.get("product_name")
                        or prod.get("generic_name_es")
                        or prod.get("generic_name")
                        or ""
                    ).strip()

                    marca = (prod.get("brands") or "").strip()
                    cant = (prod.get("quantity") or "").strip()
                    cats = (prod.get("categories") or "").strip()

                    desc_final = formatear_nombre_producto(nombre, marca, cant)
                    if not desc_final:
                        desc_final = nombre or marca

                    if not desc_final:
                        continue

                    return {
                        "descripcion": desc_final,
                        "marca": marca,
                        "cantidad": cant,
                        "categoria_texto": cats,
                        "unidad_medida": sugerir_unidad_medida(cant),
                    }
        except Exception:
            # Continuar con el siguiente o salir silenciosamente
            continue

    return None
