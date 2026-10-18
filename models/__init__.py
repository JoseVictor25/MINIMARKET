"""models/__init__.py – Registra todos los modelos para que SQLAlchemy los detecte."""

from .usuario import Usuario          # noqa
from .cliente import Cliente          # noqa
from .proveedor import Proveedor      # noqa
from .categoria import Categoria      # noqa
from .producto import Producto        # noqa
from .compra import Compra, DetalleCompra   # noqa
from .venta import Venta, DetalleVenta      # noqa
from .ajuste_inventario import AjusteInventario  # noqa
from .caja import SesionCaja          # noqa
