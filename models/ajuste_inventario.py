"""
models/ajuste_inventario.py – Ajustes manuales de stock con motivo y responsable.
"""
from decimal import Decimal
from datetime import datetime
from sqlalchemy import ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class AjusteInventario(Base):
    __tablename__ = "ajustes_inventario"

    TIPO_ENTRADA = "entrada"
    TIPO_SALIDA  = "salida"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)  # entrada / salida
    motivo: Mapped[str] = mapped_column(String(200), nullable=False)

    # Cantidad en milésimas (positiva siempre; el tipo indica dirección)
    _cantidad_m: Mapped[int] = mapped_column("cantidad_m", Integer, nullable=False)

    # FK
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)

    # Relaciones
    producto = relationship("Producto", back_populates="ajustes")
    usuario = relationship("Usuario", back_populates="ajustes")

    @property
    def cantidad(self) -> Decimal:
        return Decimal(self._cantidad_m) / 1000

    @cantidad.setter
    def cantidad(self, valor):
        self._cantidad_m = int(Decimal(str(valor)) * 1000)

    @property
    def cantidad_efectiva(self) -> Decimal:
        """Positiva = entrada, negativa = salida."""
        if self.tipo == self.TIPO_SALIDA:
            return -self.cantidad
        return self.cantidad

    def __repr__(self):
        return f"<Ajuste {self.tipo} {self.cantidad} - {self.motivo}>"
