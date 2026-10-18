# Mini Market POS – Sistema Portátil de Punto de Venta

Sistema de escritorio portable desarrollado en Python + PyQt5 + SQLite para gestión de un Mini Market.

**Compatible con: Windows 7, 8, 8.1, 10 y 11 (32 y 64 bits)**

## Credenciales por defecto

| Campo | Valor |
|---|---|
| Usuario | `admin` |
| Contraseña | `admin123` |

> ⚠️ **Cambiar la contraseña del administrador tras el primer inicio.**

---

## Requisitos del sistema (para ejecutar el instalador)

| Elemento | Requisito |
|---|---|
| **Sistema Operativo** | Windows 7 / 8 / 8.1 / 10 / 11 (32 o 64 bits) |
| **Espacio en disco** | ~200 MB |
| **RAM** | 512 MB mínimo |
| **Python** | No requerido (el ejecutable es portable) |

---

## Instalación / Distribución

### Opción A – Usar el ejecutable generado (Recomendado)

1. Copia la carpeta completa `dist\MiniMarket\` a la PC de destino
2. Ejecuta `MiniMarket.exe`
3. La base de datos `minimarket.db` se crea automáticamente al primer inicio

> 📁 **Importante:** Copiar TODA la carpeta `dist\MiniMarket\`, no solo el `.exe`

### Opción B – Generar el ejecutable tú mismo

```bat
REM Desde la carpeta del proyecto, ejecutar:
build.bat
```

O manualmente:

```powershell
# Instalar dependencias
pip install -r requirements.txt

# Generar ejecutable
pyinstaller minimarket.spec --clean

# El resultado queda en dist\MiniMarket\
```

---

## Ejecutar en desarrollo (con Python instalado)

```powershell
# En la carpeta del proyecto:
venv\Scripts\Activate.ps1
python main.py
```

O sin entorno virtual:
```powershell
pip install PyQt5 SQLAlchemy reportlab
python main.py
```

---

## Atajos de teclado (Punto de Venta)

| Tecla | Acción |
|---|---|
| `Enter` | Agregar producto por código de barras |
| `F11` | Buscar producto por nombre |
| `F12` | Confirmar / cobrar venta |
| `Esc` | Limpiar venta actual |
| `Del` | Eliminar ítem seleccionado |

---

## Estructura del proyecto

```
MINIMARKET/
├── models/           # Modelos SQLAlchemy (diagrama de clases)
│   ├── usuario.py
│   ├── cliente.py
│   ├── proveedor.py
│   ├── categoria.py
│   ├── producto.py
│   ├── venta.py
│   ├── compra.py
│   └── ajuste_inventario.py
├── services/         # Lógica transaccional de negocio
│   ├── venta_service.py
│   ├── compra_service.py
│   ├── inventario_service.py
│   └── ticket_service.py
├── ui/               # Interfaces PyQt5
│   ├── styles.py         – Tema oscuro global
│   ├── login_dialog.py   – Pantalla de login
│   ├── main_window.py    – Ventana principal + sidebar
│   ├── pos_widget.py     – Punto de Venta
│   ├── productos_widget.py
│   ├── compras_widget.py
│   ├── ventas_widget.py
│   ├── inventario_widget.py
│   ├── maestros_widget.py  – Clientes, Proveedores, Categorías
│   └── usuarios_widget.py
├── config.py         # Rutas portátiles (DB junto al .exe)
├── database.py       # Motor SQLite + SQLAlchemy
├── main.py           # Punto de entrada
├── minimarket.spec   # Configuración PyInstaller
├── build.bat         # Script para generar el ejecutable
├── requirements.txt
└── minimarket.db     # Generada al primer inicio
```

---

## Respaldo de la base de datos

En la barra lateral, hacer clic en **"💾 Respaldar BD"** para copiar el archivo `.db` con fecha y hora en la carpeta que se elija.

O manualmente copiar el archivo `minimarket.db`.

---

## Notas técnicas

- **Framework UI:** PyQt5 5.15.x – Soporta Windows 7, 8, 8.1, 10 y 11
- **Precios sin errores de float:** almacenados como enteros en centavos (`INTEGER`).
- **Stock fraccionario:** almacenado en milésimas (1000 = 1 unidad).
- **Transacciones atómicas:** venta/compra/anulación en una sola transacción SQLite.
- **Precios históricos:** `DetalleVenta` guarda el precio al momento de la venta.
- **Modo WAL:** SQLite en modo WAL para mejor concurrencia.
