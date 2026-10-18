"""
ui/productos_widget.py – CRUD completo de productos y categorías.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QFormLayout,
    QComboBox, QDoubleSpinBox, QCheckBox, QMessageBox,
    QAbstractItemView, QFrame, QSpinBox, QApplication,
    QShortcut, QStyledItemDelegate,
)

from database import SessionLocal
from models.producto import Producto
from models.categoria import Categoria
from config import CURRENCY
from ui.styles import PALETTE
from services.barcode_service import normalizar_codigo_barras, consultar_producto_online


class ReconocimientoBarcodeWorker(QThread):
    resultado = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, codigo: str):
        super().__init__()
        self.codigo = codigo

    def run(self):
        try:
            datos = consultar_producto_online(self.codigo, timeout_segundos=2.5)
            self.resultado.emit(datos or {})
        except Exception as e:
            self.error.emit(str(e))


class ProductoDialog(QDialog):
    """Formulario para crear / editar un producto con soporte de escaneo inteligente."""

    def __init__(self, session, producto=None, parent=None, codigo_inicial: str = ""):
        super().__init__(parent)
        self.session = session
        self.producto = producto
        self.codigo_inicial = codigo_inicial
        self._worker_reconocimiento: ReconocimientoBarcodeWorker | None = None

        self.setWindowTitle("📦 Registrar Producto" if not producto else "✏ Editar Producto")
        self.setFixedWidth(560)
        self._build_ui()

        if producto:
            self._cargar_datos()
        elif codigo_inicial:
            self.input_codigo.setText(codigo_inicial)
            QTimer.singleShot(100, self._procesar_codigo_escaneado)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(60, self._auto_enfocar)

    def _auto_enfocar(self):
        if not self.producto and not self.codigo_inicial:
            self.input_codigo.setFocus()
            self.input_codigo.selectAll()
        else:
            self.input_desc.setFocus()
            self.input_desc.selectAll()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        # ── Encabezado Moderno con Badge ──────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(14)

        icon_frame = QFrame()
        icon_frame.setFixedSize(48, 48)
        icon_frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0284c7, stop:1 #0ea5e9);
                border-radius: 12px;
                border: 1px solid #38bdf8;
            }}
        """)
        icon_lay = QVBoxLayout(icon_frame)
        icon_lay.setContentsMargins(0, 0, 0, 0)
        lbl_ico = QLabel("📦")
        lbl_ico.setAlignment(Qt.AlignCenter)
        lbl_ico.setStyleSheet("font-size: 24px; background: transparent; border: none;")
        icon_lay.addWidget(lbl_ico)
        hdr.addWidget(icon_frame)

        hdr_texts = QVBoxLayout()
        hdr_texts.setSpacing(2)
        lbl_tit = QLabel("Registrar Producto con Escáner" if not self.producto else "Editar Producto")
        lbl_tit.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff; background: transparent; border: none;")
        hdr_texts.addWidget(lbl_tit)

        lbl_sub = QLabel("Pase el producto por el lector o complete la información del catálogo.")
        lbl_sub.setStyleSheet("color: #94a3b8; font-size: 12px; background: transparent; border: none;")
        hdr_texts.addWidget(lbl_sub)
        hdr.addLayout(hdr_texts)
        hdr.addStretch()
        root.addLayout(hdr)

        # ── Card 1: Identificación y Categoría ─────────────────────────
        card_id = QFrame()
        card_id.setStyleSheet("""
            QFrame {
                background: #16202e;
                border: 1px solid #283548;
                border-radius: 12px;
            }
        """)
        lay_id = QVBoxLayout(card_id)
        lay_id.setContentsMargins(16, 14, 16, 14)
        lay_id.setSpacing(10)

        # Código de barras
        lbl_cod = QLabel("CÓDIGO DE BARRAS *")
        lbl_cod.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; border: none; background: transparent;")
        lay_id.addWidget(lbl_cod)

        row_codigo = QHBoxLayout()
        row_codigo.setSpacing(8)

        self.input_codigo = QLineEdit()
        self.input_codigo.setFixedHeight(40)
        self.input_codigo.setPlaceholderText("Pase el producto por el lector o escriba el código...")
        self.input_codigo.setStyleSheet(f"""
            QLineEdit {{
                font-size: 14px;
                font-weight: bold;
                padding: 6px 12px;
                background: #101722;
                border: 1.5px solid #2e3c50;
                border-radius: 8px;
                color: #ffffff;
            }}
            QLineEdit:focus {{
                border: 2px solid {PALETTE['accent']};
                background: #131c2a;
            }}
        """)
        self.input_codigo.returnPressed.connect(self._on_codigo_enter)
        row_codigo.addWidget(self.input_codigo, 1)

        self.btn_reconocer = QPushButton("🔍 Reconocer")
        self.btn_reconocer.setFixedHeight(40)
        self.btn_reconocer.setCursor(Qt.PointingHandCursor)
        self.btn_reconocer.setToolTip("Buscar automáticamente el nombre y datos del producto en internet")
        self.btn_reconocer.setStyleSheet(f"""
            QPushButton {{
                background: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: #0ea5e9;
            }}
            QPushButton:pressed {{
                background: #0369a1;
            }}
        """)
        self.btn_reconocer.clicked.connect(self._on_codigo_enter)
        row_codigo.addWidget(self.btn_reconocer)
        lay_id.addLayout(row_codigo)

        # Estado del lector / escáner
        self.lbl_scanner_status = QLabel("📷 Lector activo: Pase el producto por la máquina y presione Enter")
        self.lbl_scanner_status.setStyleSheet("""
            background: #0f172a;
            color: #38bdf8;
            font-size: 11px;
            border-radius: 6px;
            padding: 5px 10px;
            border: 1px solid #1e293b;
        """)
        lay_id.addWidget(self.lbl_scanner_status)

        # Descripción
        lbl_desc = QLabel("DESCRIPCIÓN / NOMBRE DEL PRODUCTO *")
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; border: none; background: transparent;")
        lay_id.addWidget(lbl_desc)

        self.input_desc = QLineEdit()
        self.input_desc.setFixedHeight(40)
        self.input_desc.setPlaceholderText("Nombre del producto (se autocompleta con el escáner)")
        self.input_desc.setStyleSheet(f"""
            QLineEdit {{
                font-size: 13px;
                padding: 6px 12px;
                background: #101722;
                border: 1.5px solid #2e3c50;
                border-radius: 8px;
                color: #ffffff;
            }}
            QLineEdit:focus {{
                border: 2px solid {PALETTE['accent']};
                background: #131c2a;
            }}
        """)
        self.input_desc.returnPressed.connect(lambda: self.spin_precio_venta.setFocus())
        lay_id.addWidget(self.input_desc)

        # Fila Categoría y Unidad de Medida en 2 columnas
        row_cat_um = QHBoxLayout()
        row_cat_um.setSpacing(12)

        col_cat = QVBoxLayout()
        col_cat.setSpacing(4)
        lbl_c = QLabel("CATEGORÍA *")
        lbl_c.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; border: none; background: transparent;")
        col_cat.addWidget(lbl_c)

        self.combo_cat = QComboBox()
        self.combo_cat.setFixedHeight(40)
        self.combo_cat.setItemDelegate(QStyledItemDelegate(self.combo_cat))
        self.combo_cat.setMaxVisibleItems(10)
        self.combo_cat.setStyleSheet(f"""
            QComboBox {{
                background: #101722;
                border: 1.5px solid #2e3c50;
                border-radius: 8px;
                padding: 4px 12px;
                color: #ffffff;
                font-size: 13px;
                font-weight: 500;
            }}
            QComboBox:focus {{
                border: 2px solid {PALETTE['accent']};
            }}
        """)

        # Cargar categorías ordenadas y con iconos representativos
        CAT_ICON_MAP = {
            "general": "🏷️", "bebida": "🥤", "refresco": "🥤", "snack": "🍪",
            "dulce": "🍬", "golosina": "🍬", "abarrote": "🌾", "despensa": "🌾",
            "lácteo": "🧀", "lacteo": "🧀", "huevo": "🥚", "panader": "🍞",
            "pan": "🍞", "embutido": "🥩", "carne": "🥩", "limpieza": "🧹",
            "hogar": "🧹", "cuidado": "🧴", "personal": "🧴", "aseo": "🧴",
            "licor": "🍷", "cerveza": "🍺", "fruta": "🍎", "verdura": "🥦",
            "bazar": "📦",
        }
        categorias = self.session.query(Categoria).order_by(Categoria.nombre).all()
        for cat in categorias:
            ico = "🏷️"
            nom_l = cat.nombre.lower()
            for k, sym in CAT_ICON_MAP.items():
                if k in nom_l:
                    ico = sym
                    break
            self.combo_cat.addItem(f"{ico}  {cat.nombre}", cat.id)

        col_cat.addWidget(self.combo_cat)
        row_cat_um.addLayout(col_cat, 7)

        col_um = QVBoxLayout()
        col_um.setSpacing(4)
        lbl_u = QLabel("UNIDAD")
        lbl_u.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; border: none; background: transparent;")
        col_um.addWidget(lbl_u)

        self.combo_um = QComboBox()
        self.combo_um.setFixedHeight(40)
        self.combo_um.setItemDelegate(QStyledItemDelegate(self.combo_um))
        self.combo_um.setStyleSheet(f"""
            QComboBox {{
                background: #101722;
                border: 1.5px solid #2e3c50;
                border-radius: 8px;
                padding: 4px 12px;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
            }}
            QComboBox:focus {{
                border: 2px solid {PALETTE['accent']};
            }}
        """)
        self.combo_um.addItems(["UN", "KG", "LT", "CJ", "PQ", "MT", "GR", "ML"])
        col_um.addWidget(self.combo_um)
        row_cat_um.addLayout(col_um, 3)

        lay_id.addLayout(row_cat_um)
        root.addWidget(card_id)

        # ── Card 2: Precios e Inventario (2 Columnas) ─────────────────
        card_num = QFrame()
        card_num.setStyleSheet("""
            QFrame {
                background: #16202e;
                border: 1px solid #283548;
                border-radius: 12px;
            }
        """)
        lay_num = QVBoxLayout(card_num)
        lay_num.setContentsMargins(16, 14, 16, 14)
        lay_num.setSpacing(10)

        # Fila Precios
        row_precios = QHBoxLayout()
        row_precios.setSpacing(12)

        col_compra = QVBoxLayout()
        col_compra.setSpacing(4)
        lbl_pc = QLabel(f"PRECIO DE COMPRA ({CURRENCY})")
        lbl_pc.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; border: none; background: transparent;")
        col_compra.addWidget(lbl_pc)

        self.spin_precio_compra = QDoubleSpinBox()
        self.spin_precio_compra.setFixedHeight(40)
        self.spin_precio_compra.setMaximum(999999.99)
        self.spin_precio_compra.setDecimals(2)
        self.spin_precio_compra.setSuffix(f" {CURRENCY}")
        self.spin_precio_compra.setStyleSheet(f"""
            QDoubleSpinBox {{
                font-size: 14px;
                font-weight: bold;
                padding: 4px 10px;
                background: #101722;
                border: 1.5px solid #2e3c50;
                border-radius: 8px;
                color: #ffffff;
            }}
            QDoubleSpinBox:focus {{
                border: 2px solid {PALETTE['accent']};
            }}
        """)
        col_compra.addWidget(self.spin_precio_compra)
        row_precios.addLayout(col_compra)

        col_venta = QVBoxLayout()
        col_venta.setSpacing(4)
        lbl_pv = QLabel(f"PRECIO DE VENTA ({CURRENCY}) *")
        lbl_pv.setStyleSheet(f"color: {PALETTE['accent']}; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; border: none; background: transparent;")
        col_venta.addWidget(lbl_pv)

        self.spin_precio_venta = QDoubleSpinBox()
        self.spin_precio_venta.setFixedHeight(40)
        self.spin_precio_venta.setMaximum(999999.99)
        self.spin_precio_venta.setDecimals(2)
        self.spin_precio_venta.setSuffix(f" {CURRENCY}")
        self.spin_precio_venta.setStyleSheet(f"""
            QDoubleSpinBox {{
                font-size: 14px;
                font-weight: bold;
                padding: 4px 10px;
                background: #101722;
                border: 1.5px solid {PALETTE['accent']};
                border-radius: 8px;
                color: #ffffff;
            }}
            QDoubleSpinBox:focus {{
                border: 2px solid #38bdf8;
                background: #131c2a;
            }}
        """)
        col_venta.addWidget(self.spin_precio_venta)
        row_precios.addLayout(col_venta)

        lay_num.addLayout(row_precios)

        # Indicador de rentabilidad en tiempo real
        self.lbl_margen = QLabel(f"📈 Ganancia estimada: {CURRENCY} 0.00 (0%)")
        self.lbl_margen.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        lay_num.addWidget(self.lbl_margen)

        self.spin_precio_compra.valueChanged.connect(self._actualizar_margen)
        self.spin_precio_venta.valueChanged.connect(self._actualizar_margen)

        # Fila Stocks
        row_stocks = QHBoxLayout()
        row_stocks.setSpacing(12)

        col_st = QVBoxLayout()
        col_st.setSpacing(4)
        lbl_st = QLabel("STOCK INICIAL")
        lbl_st.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; border: none; background: transparent;")
        col_st.addWidget(lbl_st)

        self.input_stock = QLineEdit("1")
        self.input_stock.setFixedHeight(40)
        self.input_stock.setPlaceholderText("Ej. 10 o 1.5")
        self.input_stock.setStyleSheet(f"""
            QLineEdit {{
                font-size: 13px;
                font-weight: bold;
                padding: 6px 12px;
                background: #101722;
                border: 1.5px solid #2e3c50;
                border-radius: 8px;
                color: #ffffff;
            }}
            QLineEdit:focus {{
                border: 2px solid {PALETTE['accent']};
            }}
        """)
        self.input_stock.returnPressed.connect(lambda: self.input_stock_min.setFocus())
        col_st.addWidget(self.input_stock)
        row_stocks.addLayout(col_st)

        col_st_min = QVBoxLayout()
        col_st_min.setSpacing(4)
        lbl_stm = QLabel("STOCK MÍNIMO (ALERTA)")
        lbl_stm.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; border: none; background: transparent;")
        col_st_min.addWidget(lbl_stm)

        self.input_stock_min = QLineEdit("5")
        self.input_stock_min.setFixedHeight(40)
        self.input_stock_min.setPlaceholderText("Ej. 5")
        self.input_stock_min.setStyleSheet(f"""
            QLineEdit {{
                font-size: 13px;
                font-weight: bold;
                padding: 6px 12px;
                background: #101722;
                border: 1.5px solid #2e3c50;
                border-radius: 8px;
                color: #ffffff;
            }}
            QLineEdit:focus {{
                border: 2px solid {PALETTE['accent']};
            }}
        """)
        self.input_stock_min.returnPressed.connect(self._guardar)
        col_st_min.addWidget(self.input_stock_min)
        row_stocks.addLayout(col_st_min)

        lay_num.addLayout(row_stocks)

        # Checkbox Activo
        self.chk_activo = QCheckBox("✓  Producto activo para venta inmediata en caja")
        self.chk_activo.setChecked(True)
        self.chk_activo.setStyleSheet("""
            QCheckBox {
                color: #f1f5f9;
                font-size: 12px;
                font-weight: 500;
                spacing: 8px;
                border: none;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1.5px solid #475569;
                background: #101722;
            }
            QCheckBox::indicator:checked {
                background: #0ea5e9;
                border-color: #38bdf8;
            }
        """)
        lay_num.addWidget(self.chk_activo)

        root.addWidget(card_num)

        # ── Botones de Acción (Footer) ─────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        btn_cancel = QPushButton("✗ Cancelar (Esc)")
        btn_cancel.setFixedHeight(44)
        btn_cancel.setAutoDefault(False)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 10px;
                font-size: 13px;
                font-weight: 600;
                padding: 0 18px;
            }
            QPushButton:hover {
                background: #334155;
                color: #ffffff;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel, 4)

        self.btn_save = QPushButton("💾 Guardar Producto")
        self.btn_save.setFixedHeight(44)
        self.btn_save.setAutoDefault(False)
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0284c7, stop:1 #0369a1);
                color: #ffffff;
                border: 1px solid #38bdf8;
                border-radius: 10px;
                font-size: 14px;
                font-weight: bold;
                letter-spacing: 0.5px;
                padding: 0 24px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0ea5e9, stop:1 #0284c7);
                border-color: #7dd3fc;
            }}
            QPushButton:pressed {{
                background: #0369a1;
            }}
        """)
        self.btn_save.clicked.connect(self._guardar)
        btn_row.addWidget(self.btn_save, 6)

        root.addLayout(btn_row)

        self.btn_reconocer.setAutoDefault(False)

        # Atajos de teclado para guardar rápidamente sin necesidad de mouse
        QShortcut(QKeySequence(Qt.Key_Return), self.spin_precio_venta, lambda: self.input_stock.setFocus())
        QShortcut(QKeySequence(Qt.Key_Enter), self.spin_precio_venta, lambda: self.input_stock.setFocus())
        QShortcut(QKeySequence(Qt.Key_Return), self.input_stock, lambda: self.input_stock_min.setFocus())
        QShortcut(QKeySequence(Qt.Key_Enter), self.input_stock, lambda: self.input_stock_min.setFocus())
        QShortcut(QKeySequence(Qt.Key_Return), self.input_stock_min, self._guardar)
        QShortcut(QKeySequence(Qt.Key_Enter), self.input_stock_min, self._guardar)
        QShortcut(QKeySequence("Ctrl+Return"), self, self._guardar)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self._guardar)

    def _actualizar_margen(self):
        compra = Decimal(str(self.spin_precio_compra.value()))
        venta = Decimal(str(self.spin_precio_venta.value()))
        ganancia = venta - compra
        if venta > 0:
            porcentaje = (ganancia / venta) * Decimal("100")
            signo = "+" if ganancia >= 0 else ""
            color = "#10b981" if ganancia >= 0 else "#f43f5e"
            self.lbl_margen.setText(f"📈 Ganancia estimada: {signo}{CURRENCY} {ganancia:.2f} ({signo}{porcentaje:.1f}%)")
            self.lbl_margen.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        else:
            self.lbl_margen.setText(f"📈 Ganancia estimada: {CURRENCY} 0.00 (0%)")
            self.lbl_margen.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; border: none; background: transparent;")

    def _on_codigo_enter(self):
        codigo = normalizar_codigo_barras(self.input_codigo.text())
        if not codigo:
            self.lbl_scanner_status.setText("⚠ Ingrese o escanee un código de barras.")
            self.lbl_scanner_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
            return

        self.input_codigo.setText(codigo)
        self._procesar_codigo_escaneado()

    def _procesar_codigo_escaneado(self):
        codigo = normalizar_codigo_barras(self.input_codigo.text())
        if not codigo:
            return

        try:
            QApplication.beep()
        except Exception:
            pass

        # 1. Verificar si ya existe en la base de datos local
        existente = self.session.query(Producto).filter_by(codigo_barras=codigo).first()
        if existente and (not self.producto or existente.id != self.producto.id):
            self.lbl_scanner_status.setText(
                f"⚠ Ya existe en el sistema: '{existente.descripcion}' ({CURRENCY} {existente.precio_venta_bs:.2f})"
            )
            self.lbl_scanner_status.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: bold;")
            resp = QMessageBox.question(
                self,
                "Producto ya registrado",
                f"El código '{codigo}' ya está asignado al producto:\n\n"
                f"• {existente.descripcion}\n"
                f"• Precio: {CURRENCY} {existente.precio_venta_bs:.2f}\n"
                f"• Stock: {existente.stock_actual}\n\n"
                "¿Desea cargar sus datos para editarlo?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if resp == QMessageBox.Yes:
                self.producto = existente
                self.setWindowTitle("✏ Editar Producto")
                self._cargar_datos()
                self.input_desc.setFocus()
            return

        # 2. Consultar datos en internet si no tiene descripción aún
        self.lbl_scanner_status.setText(f"✓ Código '{codigo}' capturado. Reconociendo producto...")
        self.lbl_scanner_status.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")

        # Si el usuario ya escribió una descripción, no sobrescribirla
        if self.input_desc.text().strip():
            self.spin_precio_venta.setFocus()
            self.spin_precio_venta.selectAll()
            return

        # Iniciar worker en segundo plano para no congelar la UI
        if self._worker_reconocimiento and self._worker_reconocimiento.isRunning():
            self._worker_reconocimiento.terminate()

        self._worker_reconocimiento = ReconocimientoBarcodeWorker(codigo)
        self._worker_reconocimiento.resultado.connect(self._on_resultado_reconocimiento)
        self._worker_reconocimiento.start()

    def _on_resultado_reconocimiento(self, datos: dict):
        if datos and datos.get("descripcion"):
            desc = datos["descripcion"]
            self.input_desc.setText(desc)

            # Unidad de medida
            um = datos.get("unidad_medida", "UN")
            idx_um = self.combo_um.findText(um)
            if idx_um >= 0:
                self.combo_um.setCurrentIndex(idx_um)

            # Categoría sugerida
            cat_txt = (datos.get("categoria_texto") or "").lower()
            if cat_txt:
                for i in range(self.combo_cat.count()):
                    cat_nom = self.combo_cat.itemText(i).lower()
                    if cat_nom in cat_txt or any(palabra in cat_txt for palabra in cat_nom.split()):
                        self.combo_cat.setCurrentIndex(i)
                        break

            self.lbl_scanner_status.setText(f"✨ ¡Producto reconocido automáticamente!: {desc}")
            self.lbl_scanner_status.setStyleSheet("color: #22c55e; font-size: 11px; font-weight: bold;")

            # Si ya se completó la descripción, enfocar el precio de venta
            self.spin_precio_venta.setFocus()
            self.spin_precio_venta.selectAll()
        else:
            codigo = self.input_codigo.text().strip()
            self.lbl_scanner_status.setText(f"✓ Código '{codigo}' asignado. Ingrese el nombre del producto.")
            self.lbl_scanner_status.setStyleSheet("color: #22c55e; font-size: 11px;")
            self.input_desc.setFocus()
            self.input_desc.selectAll()

    def _cargar_datos(self):
        p = self.producto
        self.input_codigo.setText(p.codigo_barras)
        self.input_desc.setText(p.descripcion)
        idx = self.combo_cat.findData(p.categoria_id)
        if idx >= 0:
            self.combo_cat.setCurrentIndex(idx)
        um_idx = self.combo_um.findText(p.unidad_medida)
        if um_idx >= 0:
            self.combo_um.setCurrentIndex(um_idx)
        self.spin_precio_compra.setValue(float(p.precio_compra_bs))
        self.spin_precio_venta.setValue(float(p.precio_venta_bs))
        self._actualizar_margen()

        st = p.stock_actual
        st_txt = str(int(st)) if st == int(st) else f"{st:.3f}".rstrip('0').rstrip('.')
        self.input_stock.setText(st_txt)

        st_min = p.stock_minimo
        st_min_txt = str(int(st_min)) if st_min == int(st_min) else f"{st_min:.3f}".rstrip('0').rstrip('.')
        self.input_stock_min.setText(st_min_txt)

        self.chk_activo.setChecked(p.activo)
        self.lbl_scanner_status.setText(f"✓ Editando producto: {p.descripcion}")
        self.lbl_scanner_status.setStyleSheet("color: #38bdf8; font-size: 11px;")

    def _guardar(self):
        codigo = normalizar_codigo_barras(self.input_codigo.text())
        desc   = self.input_desc.text().strip()

        if not codigo or not desc:
            QMessageBox.warning(self, "Error", "Código y descripción son obligatorios.")
            return

        if self.spin_precio_venta.value() <= 0:
            QMessageBox.warning(self, "Error", "El precio de venta debe ser mayor a 0.")
            return

        # Verificar duplicado
        existente = self.session.query(Producto).filter_by(codigo_barras=codigo).first()
        if existente and (not self.producto or existente.id != self.producto.id):
            QMessageBox.warning(self, "Error", f"Ya existe un producto con código '{codigo}'.")
            return

        if not self.producto:
            self.producto = Producto(codigo_barras=codigo)
            self.session.add(self.producto)

        # Parsear stock ingresado manualmente (acepta '10', '5', '1.5', '0.25', etc.)
        try:
            txt_st = self.input_stock.text().strip().replace(",", ".")
            val_st = Decimal(txt_st) if txt_st else Decimal("0")
            if val_st < 0:
                val_st = Decimal("0")
        except Exception:
            val_st = Decimal("0")

        try:
            txt_min = self.input_stock_min.text().strip().replace(",", ".")
            val_min = Decimal(txt_min) if txt_min else Decimal("0")
            if val_min < 0:
                val_min = Decimal("0")
        except Exception:
            val_min = Decimal("0")

        self.producto.codigo_barras = codigo
        self.producto.descripcion   = desc
        self.producto.categoria_id  = self.combo_cat.currentData()
        self.producto.unidad_medida = self.combo_um.currentText()
        self.producto.precio_compra_bs = Decimal(str(self.spin_precio_compra.value()))
        self.producto.precio_venta_bs  = Decimal(str(self.spin_precio_venta.value()))
        self.producto.stock_actual  = val_st
        self.producto.stock_minimo  = val_min
        self.producto.activo        = self.chk_activo.isChecked()

        try:
            self.session.commit()
            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "Error", f"No se pudo guardar: {e}")

    def closeEvent(self, event):
        if self._worker_reconocimiento and self._worker_reconocimiento.isRunning():
            self._worker_reconocimiento.terminate()
            self._worker_reconocimiento.wait(200)
        super().closeEvent(event)

    def reject(self):
        if self._worker_reconocimiento and self._worker_reconocimiento.isRunning():
            self._worker_reconocimiento.terminate()
            self._worker_reconocimiento.wait(200)
        super().reject()


class ProductosWidget(QWidget):
    """Panel de gestión de catálogo de productos."""

    def __init__(self, usuario=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.session = SessionLocal()
        self._build_ui()
        self._cargar_productos()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        es_admin = (self.usuario is None or self.usuario.es_admin())

        # Encabezado
        hdr = QHBoxLayout()
        lbl_titulo_txt = "Catálogo de Productos" if es_admin else "Consulta de Precios y Stock"
        lbl = QLabel(lbl_titulo_txt)
        lbl.setObjectName("subtitle")
        hdr.addWidget(lbl)
        hdr.addStretch()

        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText("🔍 Buscar por código o descripción...")
        self.input_buscar.setFixedWidth(280)
        self.input_buscar.textChanged.connect(self._filtrar)
        self.input_buscar.returnPressed.connect(self._on_enter_buscar)
        hdr.addWidget(self.input_buscar)

        btn_nuevo = QPushButton("+ Nuevo Producto")
        btn_nuevo.setObjectName("btn_primary")
        btn_nuevo.clicked.connect(self._nuevo_producto)
        hdr.addWidget(btn_nuevo)

        if not es_admin:
            btn_nuevo.hide()

        lay.addLayout(hdr)

        # Tabla
        self.tabla = QTableWidget(0, 9)
        self.tabla.setHorizontalHeaderLabels([
            "Código", "Descripción", "Categoría", "UM",
            f"P. Compra {CURRENCY}", f"P. Venta {CURRENCY}",
            "Stock", "Stock Mín.", "Estado"
        ])
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        if es_admin:
            self.tabla.doubleClicked.connect(self._editar_producto)
        self.tabla.verticalHeader().setVisible(False)

        # Si es cajero, ocultar columna 4 (P. Compra) para proteger costos
        if not es_admin:
            self.tabla.setColumnHidden(4, True)

        lay.addWidget(self.tabla, 1)

        # Botones inferiores
        btn_row = QHBoxLayout()
        btn_editar = QPushButton("✏ Editar")
        btn_editar.clicked.connect(self._editar_producto)
        btn_row.addWidget(btn_editar)

        btn_toggle = QPushButton("🚫 Desactivar / Activar")
        btn_toggle.setObjectName("btn_warning")
        btn_toggle.clicked.connect(self._toggle_activo)
        btn_row.addWidget(btn_toggle)

        if not es_admin:
            btn_editar.hide()
            btn_toggle.hide()

        btn_row.addStretch()
        self.lbl_total_prods = QLabel("")
        self.lbl_total_prods.setStyleSheet(f"color: {PALETTE['text_muted']};")
        btn_row.addWidget(self.lbl_total_prods)

        lay.addLayout(btn_row)

    def _cargar_productos(self, filtro: str = ""):
        query = self.session.query(Producto)
        if filtro:
            query = query.filter(
                Producto.descripcion.ilike(f"%{filtro}%") |
                Producto.codigo_barras.ilike(f"%{filtro}%")
            )
        productos = query.all()

        self.tabla.setRowCount(len(productos))
        for i, p in enumerate(productos):
            st_txt = str(int(p.stock_actual)) if p.stock_actual == int(p.stock_actual) else f"{p.stock_actual:.3f}".rstrip('0').rstrip('.')
            min_txt = str(int(p.stock_minimo)) if p.stock_minimo == int(p.stock_minimo) else f"{p.stock_minimo:.3f}".rstrip('0').rstrip('.')
            items = [
                p.codigo_barras,
                p.descripcion,
                p.categoria.nombre if p.categoria else "",
                p.unidad_medida,
                f"{p.precio_compra_bs:.2f}",
                f"{p.precio_venta_bs:.2f}",
                st_txt,
                min_txt,
                "✓ Activo" if p.activo else "✗ Inactivo",
            ]
            for j, val in enumerate(items):
                cell = QTableWidgetItem(val)
                if j == 6 and p.stock_bajo:  # stock bajo → naranja
                    cell.setForeground(Qt.yellow)
                self.tabla.setItem(i, j, cell)
            self.tabla.item(i, 0).setData(Qt.UserRole, p.id)

        self.lbl_total_prods.setText(f"{len(productos)} productos")

    def _filtrar(self, texto: str):
        self._cargar_productos(texto)

    def _on_enter_buscar(self):
        txt = normalizar_codigo_barras(self.input_buscar.text())
        if not txt:
            return

        # Si coincide con algún código en la tabla, seleccionarlo
        for row in range(self.tabla.rowCount()):
            cod_item = self.tabla.item(row, 0)
            if cod_item and cod_item.text().strip().lower() == txt.lower():
                self.tabla.selectRow(row)
                self.tabla.scrollToItem(cod_item)
                return

        # Si no existe en el catálogo y es admin, ofrecer registrarlo
        es_admin = (self.usuario is None or self.usuario.es_admin())
        if self.tabla.rowCount() == 0 and es_admin and len(txt) >= 4:
            resp = QMessageBox.question(
                self,
                "Producto no registrado",
                f"El código '{txt}' no está registrado en el catálogo.\n\n"
                f"¿Desea registrar este nuevo producto con la máquina ahora?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if resp == QMessageBox.Yes:
                dlg = ProductoDialog(self.session, parent=self, codigo_inicial=txt)
                if dlg.exec():
                    self.input_buscar.clear()
                    self._cargar_productos()

    def _nuevo_producto(self):
        dlg = ProductoDialog(self.session, parent=self)
        if dlg.exec():
            self._cargar_productos(self.input_buscar.text())

    def _editar_producto(self):
        row = self.tabla.currentRow()
        if row < 0:
            return
        prod_id = self.tabla.item(row, 0).data(Qt.UserRole)
        prod = self.session.get(Producto, prod_id)
        if prod:
            dlg = ProductoDialog(self.session, prod, parent=self)
            if dlg.exec():
                self._cargar_productos(self.input_buscar.text())

    def _toggle_activo(self):
        row = self.tabla.currentRow()
        if row < 0:
            return
        prod_id = self.tabla.item(row, 0).data(Qt.UserRole)
        prod = self.session.get(Producto, prod_id)
        if prod:
            prod.activo = not prod.activo
            self.session.commit()
            self._cargar_productos(self.input_buscar.text())

    def closeEvent(self, event):
        self.session.close()
        super().closeEvent(event)
