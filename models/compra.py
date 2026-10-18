"""
models/compra.py – Cabecera de compra y clase de asociación DetalleCompra.
"""
from decimal import Decimal
from datetime import datetime
from sqlalchemy import ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class DetalleCompra(Base):
    __tablename__ = "detalle_compras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras.id", ondelete="CASCADE"), nullable=False)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)

    _cantidad_m: Mapped[int] = mapped_column("cantidad_m", Integer, nullable=False)
    _precio_unitario_c: Mapped[int] = mapped_column("precio_unitario_c", Integer, nullable=False)

    # Relaciones
    compra = relationship("Compra", back_populates="detalles")
    producto = relationship("Producto", back_populates="detalles_compra")

    @property
    def cantidad(self) -> Decimal:
        return Decimal(self._cantidad_m) / 1000

    @cantidad.setter
    def cantidad(self, valor):
        self._cantidad_m = int(Decimal(str(valor)) * 1000)

    @property
    def precio_unitario_bs(self) -> Decimal:
        return Decimal(self._precio_unitario_c) / 100

    @precio_unitario_bs.setter
    def precio_unitario_bs(self, valor):
        self._precio_unitario_c = int(Decimal(str(valor)) * 100)

    @property
    def subtotal_bs(self) -> Decimal:
        return self.cantidad * self.precio_unitario_bs


class Compra(Base):
    __tablename__ = "compras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero_factura: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    observacion: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # FK
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), nullable=False)

    # Relaciones
    usuario = relationship("Usuario", back_populates="compras")
    proveedor = relationship("Proveedor", back_populates="compras")
    detalles = relationship("DetalleCompra", back_populates="compra", cascade="all, delete-orphan")

    @property
    def total_bs(self) -> Decimal:
        return sum((d.subtotal_bs for d in self.detalles), Decimal("0.00"))

    def __repr__(self):
        return f"<Compra #{self.numero_factura} {self.total_bs} Bs>"
