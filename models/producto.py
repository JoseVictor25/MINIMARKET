"""
models/producto.py – Núcleo del inventario.

Los precios y cantidades se almacenan como INTEGER en centavos
para evitar errores de punto flotante.  Las propiedades .precio_*
devuelven Decimal para uso en la lógica de negocio.
"""
from decimal import Decimal
from sqlalchemy import ForeignKey, Integer, String
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


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_barras: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(200), nullable=False)
    unidad_medida: Mapped[str] = mapped_column(String(10), nullable=False, default="UN")

    # Precios almacenados en centavos (INTEGER)
    _precio_compra_c: Mapped[int] = mapped_column("precio_compra_c", Integer, nullable=False, default=0)
    _precio_venta_c: Mapped[int] = mapped_column("precio_venta_c", Integer, nullable=False, default=0)

    # Stock almacenado en milésimas (1000 = 1 unidad) para permitir fracciones
    _stock_actual_m: Mapped[int] = mapped_column("stock_actual_m", Integer, nullable=False, default=0)
    _stock_minimo_m: Mapped[int] = mapped_column("stock_minimo_m", Integer, nullable=False, default=0)

    activo: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)

    # FK
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False)

    # Relaciones
    categoria = relationship("Categoria", back_populates="productos")
    detalles_venta = relationship("DetalleVenta", back_populates="producto")
    detalles_compra = relationship("DetalleCompra", back_populates="producto")
    ajustes = relationship("AjusteInventario", back_populates="producto")

    # ── Propiedades de precio ─────────────────────────────────────────────────
    @property
    def precio_compra_bs(self) -> Decimal:
        return _de_centavos(self._precio_compra_c)

    @precio_compra_bs.setter
    def precio_compra_bs(self, valor):
        self._precio_compra_c = _a_centavos(valor)

    @property
    def precio_venta_bs(self) -> Decimal:
        return _de_centavos(self._precio_venta_c)

    @precio_venta_bs.setter
    def precio_venta_bs(self, valor):
        self._precio_venta_c = _a_centavos(valor)

    # ── Propiedades de stock ──────────────────────────────────────────────────
    @property
    def stock_actual(self) -> Decimal:
        return Decimal(self._stock_actual_m) / 1000

    @stock_actual.setter
    def stock_actual(self, valor):
        self._stock_actual_m = int(Decimal(str(valor)) * 1000)

    @property
    def stock_minimo(self) -> Decimal:
        return Decimal(self._stock_minimo_m) / 1000

    @stock_minimo.setter
    def stock_minimo(self, valor):
        self._stock_minimo_m = int(Decimal(str(valor)) * 1000)

    @property
    def stock_bajo(self) -> bool:
        return self._stock_actual_m <= self._stock_minimo_m

    def __repr__(self):
        return f"<Producto {self.codigo_barras} - {self.descripcion}>"
