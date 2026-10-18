"""models/usuario.py – Cajeros y administradores del sistema."""
import hashlib
from typing import List
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

# Roles disponibles en el sistema
ROLES_DISPONIBLES = ["cajero", "admin"]


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(100), nullable=False)
    # rol almacena roles separados por coma, ej: "cajero" o "cajero,admin" o "admin"
    rol: Mapped[str] = mapped_column(String(100), nullable=False, default="cajero")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    qr_imagen: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)

    # Relaciones
    ventas = relationship("Venta", back_populates="usuario")
    compras = relationship("Compra", back_populates="usuario")
    ajustes = relationship("AjusteInventario", back_populates="usuario")

    # ── Helpers de Rol ────────────────────────────────────────────────────────

    def get_roles(self) -> List[str]:
        """Retorna la lista de roles normalizados asignados al usuario."""
        if not self.rol:
            return []
        roles_norm = []
        for r in self.rol.split(","):
            val = r.strip().lower()
            if not val:
                continue
            if val in ("admin", "administrador"):
                roles_norm.append("admin")
            elif val in ("cajero", "caja"):
                roles_norm.append("cajero")
            else:
                roles_norm.append(val)
        return list(dict.fromkeys(roles_norm))

    def set_roles(self, roles: List[str]):
        """Establece los roles del usuario a partir de una lista."""
        self.rol = ",".join(sorted(set(r.strip().lower() for r in roles if r.strip())))

    def tiene_rol(self, rol_buscado: str) -> bool:
        """Retorna True si el usuario tiene el rol indicado."""
        rb = rol_buscado.strip().lower()
        if rb in ("admin", "administrador"):
            rb = "admin"
        elif rb in ("cajero", "caja"):
            rb = "cajero"
        return rb in self.get_roles()

    def es_admin(self) -> bool:
        """Retorna True si el usuario tiene el rol de administrador."""
        return self.tiene_rol("admin")

    def tiene_doble_rol(self) -> bool:
        """Retorna True si el usuario tiene 2 o más roles asignados."""
        return len(self.get_roles()) >= 2

    @property
    def rol_display(self) -> str:
        """Representación legible de los roles del usuario."""
        roles = self.get_roles()
        nombres = {"cajero": "Cajero", "admin": "Administrador"}
        return " + ".join(nombres.get(r, r.capitalize()) for r in roles) if roles else "Sin rol"

    def verificar_password(self, password: str) -> bool:
        return self.password_hash == hashlib.sha256(password.encode()).hexdigest()

    def set_password(self, password: str):
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()

    def __repr__(self):
        return f"<Usuario {self.username} ({self.rol})>"
