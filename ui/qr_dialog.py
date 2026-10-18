"""
ui/qr_dialog.py – Diálogo para que cada cajero suba, configure y gestione su imagen de cobro QR,
y visualizador de comprobantes de pago.
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QFileDialog, QMessageBox,
    QSizePolicy,
)

from database import SessionLocal
from models.usuario import Usuario
from services.archivo_service import (
    guardar_qr_usuario,
    eliminar_qr_usuario,
    resolver_ruta,
)
from ui.styles import PALETTE


class GestionQRDialog(QDialog):
    """
    Diálogo para que el cajero o administrador configure y suba
    la imagen del código QR con el que cobrará a sus clientes.
    """

    qr_actualizado = pyqtSignal(str)

    def __init__(self, usuario_id: int, parent=None):
        super().__init__(parent)
        self.usuario_id = usuario_id
        self._nueva_ruta_temporal: Path | None = None
        self._qr_actual: str | None = None
        self._nombre_usuario: str = ""

        self.setWindowTitle("📱 Configurar Mi Código QR para Cobrar")
        self.setFixedSize(500, 620)
        self.setModal(True)

        self._cargar_datos_usuario()
        self._build_ui()
        self._refrescar_vista_qr()

    def _cargar_datos_usuario(self):
        with SessionLocal() as session:
            u = session.get(Usuario, self.usuario_id)
            if u:
                self._qr_actual = u.qr_imagen
                self._nombre_usuario = f"{u.nombre_completo} (@{u.username})"

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # ── Encabezado ────────────────────────────────────────────────────────
        hdr_lay = QVBoxLayout()
        hdr_lay.setSpacing(4)

        lbl_tit = QLabel("📱 Mi Código QR de Cobro")
        lbl_tit.setStyleSheet(f"font-size: 20px; font-weight: 900; color: {PALETTE['accent']};")
        hdr_lay.addWidget(lbl_tit)

        self.lbl_sub = QLabel(f"Cajero: <b>{self._nombre_usuario}</b>")
        self.lbl_sub.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px;")
        hdr_lay.addWidget(self.lbl_sub)

        lbl_desc = QLabel(
            "Sube la imagen del QR de tu banco o billetera digital (Yape, Plin, Banco Unión, BNB, etc.). "
            "Esta imagen se mostrará automáticamente a tus clientes en el Punto de Venta al cobrar con QR."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 12px; line-height: 1.4;")
        hdr_lay.addWidget(lbl_desc)

        root.addLayout(hdr_lay)

        # ── Contenedor de Vista Previa del QR ────────────────────────────────
        self.card_preview = QFrame()
        self.card_preview.setObjectName("qr_preview_card")
        self.card_preview.setStyleSheet(f"""
            QFrame#qr_preview_card {{
                background-color: {PALETTE['bg_card']};
                border: 2px dashed {PALETTE['border']};
                border-radius: 16px;
            }}
        """)
        self.card_preview.setFixedHeight(300)
        card_lay = QVBoxLayout(self.card_preview)
        card_lay.setAlignment(Qt.AlignCenter)
        card_lay.setContentsMargins(16, 16, 16, 16)
        card_lay.setSpacing(8)

        self.lbl_imagen = QLabel()
        self.lbl_imagen.setAlignment(Qt.AlignCenter)
        self.lbl_imagen.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_imagen.setStyleSheet("background: transparent; border: none;")
        card_lay.addWidget(self.lbl_imagen)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setAlignment(Qt.AlignCenter)
        self.lbl_estado.setStyleSheet("font-size: 12px; font-weight: bold; background: transparent; border: none;")
        card_lay.addWidget(self.lbl_estado)

        root.addWidget(self.card_preview)

        # ── Botones de Carga y Gestión ───────────────────────────────────────
        btn_action_lay = QHBoxLayout()
        btn_action_lay.setSpacing(10)

        self.btn_subir = QPushButton("📁 Subir / Cambiar Imagen QR")
        self.btn_subir.setFixedHeight(42)
        self.btn_subir.setCursor(Qt.PointingHandCursor)
        self.btn_subir.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['accent']};
                color: #ffffff;
                border: none;
                border-radius: 9px;
                font-size: 13px;
                font-weight: bold;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['accent_hover']};
            }}
        """)
        self.btn_subir.clicked.connect(self._seleccionar_archivo)
        btn_action_lay.addWidget(self.btn_subir, 3)

        self.btn_eliminar = QPushButton("🗑 Quitar QR")
        self.btn_eliminar.setFixedHeight(42)
        self.btn_eliminar.setCursor(Qt.PointingHandCursor)
        self.btn_eliminar.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(239, 68, 68, 0.15);
                color: #f87171;
                border: 1px solid {PALETTE['danger']};
                border-radius: 9px;
                font-size: 13px;
                font-weight: bold;
                padding: 0 14px;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['danger']};
                color: #ffffff;
            }}
            QPushButton:disabled {{
                background-color: transparent;
                color: {PALETTE['text_muted']};
                border-color: {PALETTE['border']};
            }}
        """)
        self.btn_eliminar.clicked.connect(self._eliminar_qr)
        btn_action_lay.addWidget(self.btn_eliminar, 1)

        root.addLayout(btn_action_lay)

        root.addStretch()

        # ── Barra Inferior (Guardar / Cerrar) ────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(12)

        btn_cancelar = QPushButton("Cerrar")
        btn_cancelar.setFixedHeight(44)
        btn_cancelar.setCursor(Qt.PointingHandCursor)
        btn_cancelar.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['bg_hover']};
                color: {PALETTE['text_secondary']};
                border: 1px solid {PALETTE['border']};
                border-radius: 9px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['bg_card']};
                color: {PALETTE['text_primary']};
            }}
        """)
        btn_cancelar.clicked.connect(self.reject)
        footer.addWidget(btn_cancelar, 1)

        self.btn_guardar = QPushButton("✓ Guardar QR")
        self.btn_guardar.setFixedHeight(44)
        self.btn_guardar.setCursor(Qt.PointingHandCursor)
        self.btn_guardar.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['success']};
                color: #ffffff;
                border: none;
                border-radius: 9px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #16a34a;
            }}
            QPushButton:disabled {{
                background-color: {PALETTE['bg_surface']};
                color: {PALETTE['text_muted']};
            }}
        """)
        self.btn_guardar.clicked.connect(self._guardar)
        footer.addWidget(self.btn_guardar, 2)

        root.addLayout(footer)

    def _refrescar_vista_qr(self):
        """Actualiza el contenedor visual según si hay imagen temporal, existente o ninguna."""
        ruta_a_mostrar: Path | None = None

        if self._nueva_ruta_temporal and self._nueva_ruta_temporal.exists():
            ruta_a_mostrar = self._nueva_ruta_temporal
            self.lbl_estado.setText("🟡 Nueva imagen seleccionada (presiona 'Guardar QR' para confirmar)")
            self.lbl_estado.setStyleSheet(f"color: {PALETTE['warning']};")
            self.btn_guardar.setEnabled(True)
            self.btn_eliminar.setEnabled(True)
        elif self._qr_actual:
            ruta_a_mostrar = resolver_ruta(self._qr_actual)
            if ruta_a_mostrar:
                self.lbl_estado.setText("🟢 Código QR Activo y Configurado")
                self.lbl_estado.setStyleSheet(f"color: {PALETTE['success']};")
                self.btn_eliminar.setEnabled(True)
                self.btn_guardar.setEnabled(False)
            else:
                self.lbl_estado.setText("⚠ Archivo de QR no encontrado en el disco.")
                self.lbl_estado.setStyleSheet(f"color: {PALETTE['danger']};")
                self.btn_eliminar.setEnabled(True)
                self.btn_guardar.setEnabled(False)
        else:
            self.lbl_estado.setText("⚪ Sin imagen QR configurada.")
            self.lbl_estado.setStyleSheet(f"color: {PALETTE['text_muted']};")
            self.btn_eliminar.setEnabled(False)
            self.btn_guardar.setEnabled(False)

        if ruta_a_mostrar and ruta_a_mostrar.exists():
            pix = QPixmap(str(ruta_a_mostrar))
            if not pix.isNull():
                pix_scaled = pix.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.lbl_imagen.setPixmap(pix_scaled)
                self.card_preview.setStyleSheet(f"""
                    QFrame#qr_preview_card {{
                        background-color: #ffffff;
                        border: 3px solid {PALETTE['accent']};
                        border-radius: 16px;
                    }}
                """)
                return

        # Placeholder vacío
        self.lbl_imagen.setPixmap(QPixmap())
        self.lbl_imagen.setText("📷\n\nNo has subido una imagen QR aún.\nHaz clic en 'Subir / Cambiar Imagen QR'")
        self.lbl_imagen.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 13px; font-weight: 500;")
        self.card_preview.setStyleSheet(f"""
            QFrame#qr_preview_card {{
                background-color: {PALETTE['bg_card']};
                border: 2px dashed {PALETTE['border']};
                border-radius: 16px;
            }}
        """)

    def _seleccionar_archivo(self):
        archivo, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Imagen de Código QR",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp);;Todos los archivos (*.*)",
        )
        if not archivo:
            return

        p = Path(archivo)
        if not p.exists():
            QMessageBox.warning(self, "Error", "El archivo seleccionado no existe.")
            return

        self._nueva_ruta_temporal = p
        self._refrescar_vista_qr()

    def _eliminar_qr(self):
        resp = QMessageBox.question(
            self,
            "Quitar Código QR",
            "¿Desea eliminar la imagen de código QR actual?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        self._nueva_ruta_temporal = None
        try:
            with SessionLocal() as session:
                u = session.get(Usuario, self.usuario_id)
                if u and u.qr_imagen:
                    eliminar_qr_usuario(u.qr_imagen)
                    u.qr_imagen = None
                    session.commit()
            self._qr_actual = None
            self._refrescar_vista_qr()
            self.qr_actualizado.emit("")
            QMessageBox.information(self, "QR Eliminado", "Se ha removido el código QR.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo eliminar el QR: {e}")

    def _guardar(self):
        if not self._nueva_ruta_temporal:
            self.accept()
            return

        try:
            # Copiar imagen a la carpeta qrs/ y obtener ruta relativa
            rel_path = guardar_qr_usuario(self.usuario_id, self._nueva_ruta_temporal)

            with SessionLocal() as session:
                u = session.get(Usuario, self.usuario_id)
                if u:
                    u.qr_imagen = rel_path
                    session.commit()

            self._qr_actual = rel_path
            self._nueva_ruta_temporal = None
            self._refrescar_vista_qr()
            self.qr_actualizado.emit(rel_path)

            QMessageBox.information(
                self,
                "QR Guardado",
                "¡Tu imagen de código QR ha sido guardada con éxito!\n"
                "Ahora se mostrará a los clientes al cobrar con QR.",
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar la imagen: {e}")


class VisualizadorImagenDialog(QDialog):
    """Diálogo emergente para visualizar imágenes de comprobantes o QR en tamaño completo y responsive."""

    def __init__(self, ruta_imagen: str | Path, titulo: str = "Comprobante de Pago", parent=None):
        super().__init__(parent)
        self.ruta_imagen = Path(ruta_imagen)
        self.setWindowTitle(f"👁 {titulo}")
        self.setMinimumSize(540, 620)
        self.resize(720, 800)
        self.setModal(True)
        # Permitir maximizar para ver en pantalla completa
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self._pixmap_original: QPixmap | None = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        # Marco de imagen
        self.frame_img = QFrame()
        self.frame_img.setStyleSheet(f"""
            background-color: #0b0f19;
            border: 1px solid {PALETTE['border']};
            border-radius: 12px;
        """)
        f_lay = QVBoxLayout(self.frame_img)
        f_lay.setContentsMargins(10, 10, 10, 10)

        self.lbl_img = QLabel()
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        ruta_real = resolver_ruta(self.ruta_imagen)
        if ruta_real and ruta_real.exists():
            pix = QPixmap(str(ruta_real))
            if not pix.isNull():
                self._pixmap_original = pix
                self.lbl_img.setPixmap(pix.scaled(660, 660, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.lbl_img.setText("Error al renderizar imagen.")
        else:
            self.lbl_img.setText(f"No se encontró el archivo:\n{self.ruta_imagen}")
            self.lbl_img.setStyleSheet("color: #ef4444; font-size: 13px;")

        f_lay.addWidget(self.lbl_img)
        lay.addWidget(self.frame_img, 1)

        # Botones
        btns = QHBoxLayout()
        btn_abrir_ext = QPushButton("📂 Abrir en visor de Windows")
        btn_abrir_ext.setFixedHeight(40)
        btn_abrir_ext.setCursor(Qt.PointingHandCursor)
        btn_abrir_ext.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['bg_hover']};
                color: {PALETTE['accent']};
                border: 1px solid {PALETTE['border']};
                border-radius: 8px;
                font-weight: bold;
                padding: 0 14px;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['accent']};
                color: #ffffff;
            }}
        """)
        btn_abrir_ext.clicked.connect(self._abrir_externo)
        btns.addWidget(btn_abrir_ext)

        btns.addStretch()

        btn_cerrar = QPushButton("Cerrar (Esc)")
        btn_cerrar.setFixedHeight(40)
        btn_cerrar.setCursor(Qt.PointingHandCursor)
        btn_cerrar.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['bg_card']};
                color: {PALETTE['text_primary']};
                border: 1px solid {PALETTE['border']};
                border-radius: 8px;
                padding: 0 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['bg_hover']};
            }}
        """)
        btn_cerrar.clicked.connect(self.accept)
        btns.addWidget(btn_cerrar)

        lay.addLayout(btns)

    def _actualizar_pixmap(self):
        if not self._pixmap_original or self._pixmap_original.isNull():
            return
        target_w = max(200, self.frame_img.width() - 20)
        target_h = max(200, self.frame_img.height() - 20)
        self.lbl_img.setPixmap(
            self._pixmap_original.scaled(
                target_w, target_h,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._actualizar_pixmap()

    def _abrir_externo(self):
        ruta_real = resolver_ruta(self.ruta_imagen)
        if ruta_real and ruta_real.exists():
            try:
                os.startfile(str(ruta_real))
            except Exception as e:
                QMessageBox.warning(self, "Error", f"No se pudo abrir el archivo: {e}")
