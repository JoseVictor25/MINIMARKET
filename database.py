"""
database.py – Motor SQLite + SQLAlchemy.

- Habilita claves foráneas (PRAGMA foreign_keys=ON) en cada conexión.
- Expone SessionLocal para uso directo y get_session() como context manager.
- init_db() crea las tablas si no existen y siembra datos iniciales.
"""
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import DB_PATH


# ── Motor ─────────────────────────────────────────────────────────────────────
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _activar_fk(dbapi_conn, _):
    """Habilita integridad referencial en SQLite."""
    dbapi_conn.execute("PRAGMA foreign_keys=ON")
    dbapi_conn.execute("PRAGMA journal_mode=WAL")


# ── Sesión ────────────────────────────────────────────────────────────────────
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def get_session():
    """Context manager que garantiza commit/rollback automático."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── Base declarativa ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Inicialización ────────────────────────────────────────────────────────────
def init_db():
    """Crea todas las tablas y siembra datos iniciales si la BD está vacía."""
    import models  # noqa: importación necesaria para registrar los modelos

    Base.metadata.create_all(engine)

    # Migración segura para columnas nuevas en SQLite
    try:
        with engine.connect() as conn:
            # Columnas nuevas en ventas
            res = conn.execute(text("PRAGMA table_info(ventas)")).fetchall()
            columnas = [row[1] for row in res]
            if "sesion_caja_id" not in columnas:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN sesion_caja_id INTEGER REFERENCES sesiones_caja(id)"))
            if "qr_confirmado" not in columnas:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN qr_confirmado BOOLEAN DEFAULT 0"))
            if "referencia_pago" not in columnas:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN referencia_pago VARCHAR(100)"))
            if "comprobante_pago" not in columnas:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN comprobante_pago VARCHAR(500)"))

            # Columnas nuevas en usuarios
            res_u = conn.execute(text("PRAGMA table_info(usuarios)")).fetchall()
            columnas_u = [row[1] for row in res_u]
            if "qr_imagen" not in columnas_u:
                conn.execute(text("ALTER TABLE usuarios ADD COLUMN qr_imagen VARCHAR(500)"))

            conn.commit()
    except Exception:
        pass

    _seed(SessionLocal())


def _seed(session):
    """Inserta registros mínimos para arrancar el sistema."""
    from models.usuario import Usuario
    from models.categoria import Categoria
    import hashlib

    try:
        # Usuario admin por defecto
        if not session.query(Usuario).first():
            admin = Usuario(
                username="admin",
                password_hash=hashlib.sha256(b"admin123").hexdigest(),
                nombre_completo="Administrador",
                rol="admin",
                activo=True,
            )
            session.add(admin)

        # Categorías predeterminadas para Mini Market
        categorias_default = [
            ("General", "Productos generales y varios"),
            ("Bebidas y Refrescos", "Gaseosas, jugos, aguas y energizantes"),
            ("Snacks y Golosinas", "Galletas, papas, chocolates y dulces"),
            ("Abarrotes y Despensa", "Arroz, azúcar, fideos, aceites y conservas"),
            ("Lácteos y Huevos", "Leches, yogures, quesos y mantequillas"),
            ("Panadería y Galletas", "Panes, tostadas y bollería"),
            ("Embutidos y Fiambres", "Jamones, salchichas y embutidos"),
            ("Limpieza del Hogar", "Detergentes, lavavajillas y desinfectantes"),
            ("Cuidado Personal", "Jabones, champús, pastas dentales y aseo"),
            ("Licores y Cervezas", "Cervezas, vinos y bebidas alcohólicas"),
            ("Frutas y Verduras", "Productos frescos del día"),
            ("Bazar y Varios", "Pilas, encendedores, bolsas y artículos de bazar"),
        ]

        nombres_existentes = {c[0].strip().lower() for c in session.query(Categoria.nombre).all()}
        for nombre, desc in categorias_default:
            if nombre.strip().lower() not in nombres_existentes:
                session.add(Categoria(nombre=nombre, descripcion=desc))

        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
