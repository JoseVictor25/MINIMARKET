"""
models/venta.py – Cabecera de venta y clase de asociación DetalleVenta.

Los totales son propiedades derivadas calculadas desde los detalles.
El precio_unitario_bs en DetalleVenta preserva el precio histórico.
"""
from decimal import Decimal
from datetime import datetime
from sqlalchemy import Boolean, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class DetalleVenta(Base):
    __tablename__ = "detalle_ventas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id", ondelete="CASCADE"), nullable=False)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)

    # Cantidad en milésimas (1000 = 1 UN)
    _cantidad_m: Mapped[int] = mapped_column("cantidad_m", Integer, nullable=False)
    # Precio unitario histórico en centavos
    _precio_unitario_c: Mapped[int] = mapped_column("precio_unitario_c", Integer, nullable=False)

    # Relaciones
    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto", back_populates="detalles_venta")

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
        """Derivado: cantidad × precio_unitario."""
        return self.cantidad * self.precio_unitario_bs


class Venta(Base):
    __tablename__ = "ventas"

    # Estados posibles
    ESTADO_COMPLETADA = "completada"
    ESTADO_ANULADA    = "anulada"
    ESTADO_PENDIENTE  = "pendiente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero_transaccion: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default=ESTADO_COMPLETADA)
    metodo_pago: Mapped[str] = mapped_column(String(30), nullable=False, default="efectivo")
    observacion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    qr_confirmado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    referencia_pago: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    comprobante_pago: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)

    # FK
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True)
    sesion_caja_id: Mapped[int | None] = mapped_column(ForeignKey("sesiones_caja.id"), nullable=True)

    # Relaciones
    usuario = relationship("Usuario", back_populates="ventas")
    cliente = relationship("Cliente", back_populates="ventas")
    sesion_caja = relationship("SesionCaja", back_populates="ventas")
    detalles = relationship("DetalleVenta", back_populates="venta", cascade="all, delete-orphan")

    @property
    def total_bs(self) -> Decimal:
        """Derivado: suma de subtotales de todos los detalles."""
        return sum((d.subtotal_bs for d in self.detalles), Decimal("0.00"))

    def __repr__(self):
        return f"<Venta #{self.numero_transaccion} {self.estado} {self.total_bs} Bs>"
