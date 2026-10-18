"""
models/caja.py – Modelo de Sesión de Caja (Apertura, Cierre y Arqueo).
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from sqlalchemy import ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _a_centavos(valor: Decimal | float | str | None) -> int:
    """Convierte Bs a centavos enteros."""
    if valor is None:
        return 0
    return int(Decimal(str(valor)) * 100)


def _de_centavos(centavos: int | None) -> Decimal:
    """Convierte centavos enteros a Decimal en Bs."""
    if centavos is None:
        return Decimal("0.00")
    return Decimal(centavos) / 100


class SesionCaja(Base):
    __tablename__ = "sesiones_caja"

    ESTADO_ABIERTA = "abierta"
    ESTADO_CERRADA = "cerrada"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)

    fecha_apertura: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    turno: Mapped[str] = mapped_column(String(50), nullable=False, default="Mañana")
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default=ESTADO_ABIERTA)

    # Montos en centavos para precisión exacta
    _monto_inicial_c: Mapped[int] = mapped_column("monto_inicial_c", Integer, nullable=False, default=0)
    _monto_final_efectivo_c: Mapped[int | None] = mapped_column("monto_final_efectivo_c", Integer, nullable=True)
    _diferencia_c: Mapped[int | None] = mapped_column("diferencia_c", Integer, nullable=True)

    observacion: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Relaciones
    usuario = relationship("Usuario")
    ventas = relationship("Venta", back_populates="sesion_caja")

    @property
    def monto_inicial_bs(self) -> Decimal:
        return _de_centavos(self._monto_inicial_c)

    @monto_inicial_bs.setter
    def monto_inicial_bs(self, valor):
        self._monto_inicial_c = _a_centavos(valor)

    @property
    def monto_final_efectivo_bs(self) -> Decimal | None:
        if self._monto_final_efectivo_c is None:
            return None
        return _de_centavos(self._monto_final_efectivo_c)

    @monto_final_efectivo_bs.setter
    def monto_final_efectivo_bs(self, valor):
        if valor is None:
            self._monto_final_efectivo_c = None
        else:
            self._monto_final_efectivo_c = _a_centavos(valor)

    @property
    def diferencia_bs(self) -> Decimal | None:
        if self._diferencia_c is None:
            return None
        return _de_centavos(self._diferencia_c)

    @diferencia_bs.setter
    def diferencia_bs(self, valor):
        if valor is None:
            self._diferencia_c = None
        else:
            self._diferencia_c = _a_centavos(valor)

    def __repr__(self):
        return f"<SesionCaja #{self.id} {self.turno} ({self.estado}) Base: {self.monto_inicial_bs} Bs>"
