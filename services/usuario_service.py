"""
services/usuario_service.py – Autenticación y validación de nombres de usuario.

Centraliza la comparación de usernames sin distinguir mayúsculas/minúsculas
(casefold) para que login, auto-login y alta/edición de usuarios usen el mismo
criterio. La contraseña se sigue verificando con el hash actual, por lo que
sigue siendo sensible a mayúsculas y minúsculas.
"""
from __future__ import annotations

from typing import Dict, List

from sqlalchemy.orm import Session

from models.usuario import Usuario


class UsernameAmbiguoError(Exception):
    """Se produce cuando varias cuentas comparten el mismo username al normalizarlo."""

    def __init__(self, candidatos: List[Usuario]):
        self.candidatos = list(candidatos)
        detalle = ", ".join(
            f"'{u.username}' (ID {u.id})" for u in self.candidatos
        )
        super().__init__(
            "Existen varias cuentas con el mismo nombre de usuario si se ignoran "
            f"las mayúsculas/minúsculas: {detalle}."
        )


def normalizar_username(username: str | None) -> str:
    """Normaliza un username para comparaciones: sin espacios externos y casefold."""
    return (username or "").strip().casefold()


def buscar_usuarios_por_username(
    session: Session,
    username: str,
    solo_activos: bool = False,
) -> List[Usuario]:
    """
    Devuelve todas las cuentas cuyo username coincide sin distinguir
    mayúsculas/minúsculas. Se compara en Python con casefold() para cubrir
    también caracteres no ASCII.
    """
    objetivo = normalizar_username(username)
    if not objetivo:
        return []

    query = session.query(Usuario)
    if solo_activos:
        query = query.filter(Usuario.activo == True)  # noqa: E712

    return [
        u for u in query.all()
        if normalizar_username(u.username) == objetivo
    ]


def autenticar_usuario(
    session: Session,
    username: str,
    password: str,
) -> Usuario | None:
    """
    Autentica por username sin distinguir mayúsculas/minúsculas.

    - Si no existe la cuenta, retorna None.
    - Si hay más de una cuenta equivalente, lanza UsernameAmbiguoError y no
      autentica a ninguna (evita iniciar sesión en la cuenta equivocada).
    - La contraseña se valida con el hash actual (sensible a mayúsculas).
    """
    if not normalizar_username(username) or not password:
        return None

    candidatos = buscar_usuarios_por_username(session, username, solo_activos=True)
    if not candidatos:
        return None
    if len(candidatos) > 1:
        raise UsernameAmbiguoError(candidatos)

    usuario = candidatos[0]
    return usuario if usuario.verificar_password(password) else None


def usuario_unico_por_username(session: Session, username: str) -> Usuario | None:
    """
    Retorna la cuenta activa única que coincide sin distinguir mayúsculas.
    Si no existe o hay ambigüedad, retorna None (usado por el auto-login).
    """
    candidatos = buscar_usuarios_por_username(session, username, solo_activos=True)
    if len(candidatos) != 1:
        return None
    return candidatos[0]


def username_disponible(
    session: Session,
    username: str,
    excluir_id: int | None = None,
) -> bool:
    """
    Indica si un username puede usarse. Rechaza cualquier variante que difiera
    solo en mayúsculas/minúsculas, ignorando opcionalmente el propio usuario
    que se está editando.
    """
    if not normalizar_username(username):
        return False
    for usuario in buscar_usuarios_por_username(session, username):
        if excluir_id is None or usuario.id != excluir_id:
            return False
    return True


def detectar_duplicados_username(session: Session) -> Dict[str, List[Usuario]]:
    """
    Detecta cuentas duplicadas por diferencias de mayúsculas/minúsculas.
    Retorna {username_normalizado: [usuarios]} solo para los grupos con más de uno.
    No elimina ni fusiona registros.
    """
    grupos: Dict[str, List[Usuario]] = {}
    for usuario in session.query(Usuario).order_by(Usuario.id).all():
        clave = normalizar_username(usuario.username)
        if not clave:
            continue
        grupos.setdefault(clave, []).append(usuario)
    return {clave: usuarios for clave, usuarios in grupos.items() if len(usuarios) > 1}
