"""
ui/usuarios_widget.py – Gestión de usuarios del sistema (solo admins),
con soporte para configuración de código QR de cobro por cajero.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QFormLayout, QLineEdit,
    QComboBox, QCheckBox, QMessageBox, QAbstractItemView,
    QFileDialog, QFrame, QGroupBox,
)

from database import SessionLocal
from models.usuario import Usuario, ROLES_DISPONIBLES
from services.archivo_service import (
    guardar_qr_usuario,
    eliminar_qr_usuario,
    resolver_ruta,
)
from services.usuario_service import (
    detectar_duplicados_username,
    username_disponible,
)
from ui.styles import PALETTE


class UsuarioDialog(QDialog):
    def __init__(self, session, usuario=None, parent=None):
        super().__init__(parent)
        self.session = session
        self.usuario = usuario
        self._temp_qr_path: Path | None = None
        self._quitar_qr_flag = False

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Nuevo Usuario" if not usuario else f"Editar Usuario: {usuario.username}")
        self.setFixedWidth(500)
        self.setModal(True)
        self._build_ui()
        if usuario:
            self._cargar_datos()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Encabezado Estilizado ─────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("user_header")
        header.setStyleSheet(f"""
            #user_header {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {PALETTE['bg_card']}, stop:1 #1e293b);
                border-bottom: 1px solid {PALETTE['border']};
            }}
        """)
        header_lay = QHBoxLayout(header)
        header_lay.setContentsMargins(22, 16, 22, 16)
        header_lay.setSpacing(14)

        icon_badge = QLabel("👤")
        icon_badge.setObjectName("user_badge")
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setFixedSize(46, 46)
        icon_badge.setStyleSheet("""
            #user_badge {
                background-color: rgba(14, 165, 233, 0.15);
                border: 2px solid rgba(14, 165, 233, 0.4);
                border-radius: 23px;
                font-size: 22px;
            }
        """)
        header_lay.addWidget(icon_badge)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("Nuevo Usuario" if not self.usuario else f"Editar Usuario: {self.usuario.username}")
        lbl_title.setStyleSheet("font-size: 17px; font-weight: bold; color: #ffffff; border: none;")
        lbl_sub = QLabel(
            "Configure las credenciales de acceso y permisos del sistema"
            if not self.usuario else
            "Modifique los datos de acceso, roles o código QR"
        )
        lbl_sub.setStyleSheet(f"font-size: 12px; color: {PALETTE['text_secondary']}; border: none;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header_lay.addLayout(title_box)
        header_lay.addStretch()

        root.addWidget(header)

        # ── Cuerpo del Formulario ─────────────────────────────────────────────
        body = QWidget()
        form_lay = QVBoxLayout(body)
        form_lay.setContentsMargins(24, 16, 24, 16)
        form_lay.setSpacing(12)

        # Campo: Nombre de Usuario
        lbl_u = QLabel("Nombre de Usuario *")
        lbl_u.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {PALETTE['text_secondary']}; border: none;")
        form_lay.addWidget(lbl_u)

        self.input_username = QLineEdit()
        self.input_username.setFixedHeight(35)
        self.input_username.setPlaceholderText("Ej. cajero1, admin2")
        form_lay.addWidget(self.input_username)

        # Campo: Nombre Completo
        lbl_n = QLabel("Nombre Completo *")
        lbl_n.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {PALETTE['text_secondary']}; border: none;")
        form_lay.addWidget(lbl_n)

        self.input_nombre = QLineEdit()
        self.input_nombre.setFixedHeight(35)
        self.input_nombre.setPlaceholderText("Ej. José Víctor Ugarteche")
        form_lay.addWidget(self.input_nombre)

        # Campo: Roles
        lbl_r = QLabel("Roles y Permisos de Acceso *")
        lbl_r.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {PALETTE['text_secondary']}; border: none;")
        form_lay.addWidget(lbl_r)

        roles_card = QFrame()
        roles_card.setObjectName("roles_card")
        roles_card.setStyleSheet(f"""
            #roles_card {{
                background-color: {PALETTE['bg_card']};
                border: 1px solid {PALETTE['border']};
                border-radius: 8px;
            }}
            #roles_card QCheckBox {{
                background: transparent;
                border: none;
            }}
        """)
        roles_lay = QHBoxLayout(roles_card)
        roles_lay.setContentsMargins(14, 8, 14, 8)
        roles_lay.setSpacing(24)

        self._chk_roles: dict[str, QCheckBox] = {}
        for rol_id in ROLES_DISPONIBLES:
            nombre = {"cajero": "🛒 Cajero", "admin": "🛡️ Administrador"}.get(rol_id, rol_id.capitalize())
            chk = QCheckBox(nombre)
            chk.setCursor(Qt.PointingHandCursor)
            chk.setStyleSheet(f"""
                QCheckBox {{
                    color: {PALETTE['text_primary']};
                    font-size: 13px;
                    font-weight: 600;
                    background: transparent;
                    spacing: 8px;
                }}
            """)
            self._chk_roles[rol_id] = chk
            roles_lay.addWidget(chk)
        roles_lay.addStretch()

        if not self.usuario:
            self._chk_roles["cajero"].setChecked(True)

        form_lay.addWidget(roles_card)

        # Campo: Contraseña
        lbl_p = QLabel("Contraseña de Acceso" if self.usuario else "Contraseña de Acceso *")
        lbl_p.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {PALETTE['text_secondary']}; border: none;")
        form_lay.addWidget(lbl_p)

        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_pass.setFixedHeight(35)
        self.input_pass.setPlaceholderText("Dejar vacío para mantener la actual" if self.usuario else "Ingrese la contraseña *")
        form_lay.addWidget(self.input_pass)

        # Campo: Usuario Activo
        activo_card = QFrame()
        activo_card.setObjectName("activo_card")
        activo_card.setStyleSheet(f"""
            #activo_card {{
                background-color: {PALETTE['bg_card']};
                border: 1px solid {PALETTE['border']};
                border-radius: 8px;
            }}
            #activo_card QCheckBox {{
                background: transparent;
                border: none;
            }}
        """)
        activo_lay = QVBoxLayout(activo_card)
        activo_lay.setContentsMargins(14, 8, 14, 8)
        activo_lay.setSpacing(2)

        self.chk_activo = QCheckBox("Usuario activo en el sistema")
        self.chk_activo.setChecked(True)
        self.chk_activo.setCursor(Qt.PointingHandCursor)
        self.chk_activo.setStyleSheet(f"""
            QCheckBox {{
                color: {PALETTE['text_primary']};
                font-size: 13px;
                font-weight: 600;
                background: transparent;
                spacing: 8px;
            }}
        """)
        lbl_activo_hint = QLabel("Permite al usuario iniciar sesión y operar en el sistema.")
        lbl_activo_hint.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px; margin-left: 26px; background: transparent; border: none;")
        activo_lay.addWidget(self.chk_activo)
        activo_lay.addWidget(lbl_activo_hint)
        form_lay.addWidget(activo_card)

        # Campo: Código QR
        lbl_qr = QLabel("Código QR de Cobro (Opcional)")
        lbl_qr.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {PALETTE['text_secondary']}; border: none;")
        form_lay.addWidget(lbl_qr)

        qr_card = QFrame()
        qr_card.setObjectName("qr_card")
        qr_card.setStyleSheet(f"""
            #qr_card {{
                background-color: {PALETTE['bg_card']};
                border: 1px solid {PALETTE['border']};
                border-radius: 8px;
            }}
        """)
        qr_lay = QHBoxLayout(qr_card)
        qr_lay.setContentsMargins(14, 8, 14, 8)
        qr_lay.setSpacing(10)

        self.lbl_qr_preview = QLabel("⚪ Sin código QR asignado")
        self.lbl_qr_preview.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px; font-weight: 600; background: transparent; border: none;")
        qr_lay.addWidget(self.lbl_qr_preview)
        qr_lay.addStretch()

        self.btn_subir_qr = QPushButton("📁 Subir QR")
        self.btn_subir_qr.setFixedHeight(30)
        self.btn_subir_qr.setCursor(Qt.PointingHandCursor)
        self.btn_subir_qr.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['bg_hover']};
                color: {PALETTE['accent_hover']};
                border: 1px solid {PALETTE['accent_dark']};
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['accent']};
                color: #ffffff;
            }}
        """)
        self.btn_subir_qr.clicked.connect(self._seleccionar_qr)
        qr_lay.addWidget(self.btn_subir_qr)

        self.btn_quitar_qr = QPushButton("✕ Quitar")
        self.btn_quitar_qr.setFixedHeight(30)
        self.btn_quitar_qr.setCursor(Qt.PointingHandCursor)
        self.btn_quitar_qr.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(239, 68, 68, 0.15);
                color: #ef4444;
                border: 1px solid rgba(239, 68, 68, 0.4);
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['danger']};
                color: #ffffff;
            }}
        """)
        self.btn_quitar_qr.clicked.connect(self._quitar_qr)
        self.btn_quitar_qr.hide()
        qr_lay.addWidget(self.btn_quitar_qr)

        form_lay.addWidget(qr_card)
        root.addWidget(body)

        # ── Barra de Botones Inferior ─────────────────────────────────────────
        footer = QFrame()
        footer.setObjectName("user_footer")
        footer.setStyleSheet(f"""
            #user_footer {{
                background-color: {PALETTE['bg_surface']};
                border-top: 1px solid {PALETTE['border']};
            }}
        """)
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(24, 14, 24, 16)
        footer_lay.setSpacing(12)
        footer_lay.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setFixedSize(110, 38)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['bg_hover']};
                color: {PALETTE['text_primary']};
                border: 1px solid {PALETTE['border']};
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['border']};
                color: #ffffff;
            }}
        """)
        btn_cancel.clicked.connect(self.reject)
        footer_lay.addWidget(btn_cancel)

        btn_save = QPushButton("✓ Guardar Usuario")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setFixedHeight(38)
        btn_save.setMinimumWidth(155)
        btn_save.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {PALETTE['accent']}, stop:1 {PALETTE['accent_dark']});
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: {PALETTE['accent_hover']};
            }}
            QPushButton:pressed {{
                background: {PALETTE['accent_dark']};
            }}
        """)
        btn_save.clicked.connect(self._guardar)
        footer_lay.addWidget(btn_save)

        root.addWidget(footer)

    def _seleccionar_qr(self):
        arch, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Imagen de QR",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp);;Todos los archivos (*.*)",
        )
        if arch:
            self._temp_qr_path = Path(arch)
            self._quitar_qr_flag = False
            self.lbl_qr_preview.setText(f"🟢 Nuevo: {self._temp_qr_path.name}")
            self.lbl_qr_preview.setStyleSheet(f"color: {PALETTE['warning']}; font-size: 12px; font-weight: bold;")
            self.btn_quitar_qr.show()

    def _quitar_qr(self):
        self._temp_qr_path = None
        self._quitar_qr_flag = True
        self.lbl_qr_preview.setText("⚪ Sin código QR asignado")
        self.lbl_qr_preview.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px; font-weight: 600;")
        self.btn_quitar_qr.hide()

    def _cargar_datos(self):
        self.input_username.setText(self.usuario.username)
        self.input_nombre.setText(self.usuario.nombre_completo)

        # Marcar los checkboxes según los roles actuales del usuario
        roles_actuales = self.usuario.get_roles()
        for rol_id, chk in self._chk_roles.items():
            chk.setChecked(rol_id in roles_actuales)

        self.chk_activo.setChecked(self.usuario.activo)

        if self.usuario.qr_imagen:
            p = resolver_ruta(self.usuario.qr_imagen)
            if p and p.exists():
                self.lbl_qr_preview.setText(f"🟢 QR Asignado ({p.name})")
                self.lbl_qr_preview.setStyleSheet(f"color: {PALETTE['success']}; font-size: 12px; font-weight: bold;")
                self.btn_quitar_qr.show()
            else:
                self.lbl_qr_preview.setText("⚠ Archivo no encontrado")
                self.lbl_qr_preview.setStyleSheet(f"color: {PALETTE['danger']}; font-size: 12px;")
                self.btn_quitar_qr.show()

    def _guardar(self):
        username = self.input_username.text().strip()
        nombre   = self.input_nombre.text().strip()
        password = self.input_pass.text()

        if not username or not nombre:
            QMessageBox.warning(self, "Error", "Usuario y nombre son obligatorios.")
            return
        if not self.usuario and not password:
            QMessageBox.warning(self, "Error", "Ingrese una contraseña para el nuevo usuario.")
            return

        # Verificar duplicado sin distinguir mayúsculas/minúsculas.
        # 'admin', 'ADMIN' y 'Admin' se consideran el mismo nombre.
        excluir_id = self.usuario.id if self.usuario else None
        if not username_disponible(self.session, username, excluir_id=excluir_id):
            QMessageBox.warning(
                self,
                "Usuario duplicado",
                f"Ya existe una cuenta con un nombre de usuario equivalente a '{username}'.\n\n"
                "La comparación no distingue mayúsculas/minúsculas, por lo que "
                "'admin', 'ADMIN' y 'Admin' se consideran el mismo usuario.\n"
                "Elija un nombre de usuario diferente.",
            )
            return

        # Obtener roles seleccionados
        roles_seleccionados = [rid for rid, chk in self._chk_roles.items() if chk.isChecked()]
        if not roles_seleccionados:
            QMessageBox.warning(self, "Error", "Debe asignar al menos un rol al usuario.")
            return

        if not self.usuario:
            self.usuario = Usuario()
            self.session.add(self.usuario)

        self.usuario.username        = username
        self.usuario.nombre_completo = nombre
        self.usuario.set_roles(roles_seleccionados)
        self.usuario.activo          = self.chk_activo.isChecked()
        if password:
            self.usuario.set_password(password)

        try:
            self.session.flush()

            # Gestión de QR
            if self._quitar_qr_flag:
                if self.usuario.qr_imagen:
                    eliminar_qr_usuario(self.usuario.qr_imagen)
                    self.usuario.qr_imagen = None
            elif self._temp_qr_path and self._temp_qr_path.exists():
                rel = guardar_qr_usuario(self.usuario.id, self._temp_qr_path)
                self.usuario.qr_imagen = rel

            self.session.commit()
            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "Error", f"No se pudo guardar: {e}")


class UsuariosWidget(QWidget):
    """Panel de gestión de usuarios (solo admins)."""

    def __init__(self, usuario_actual: Usuario, parent=None):
        super().__init__(parent)
        self.usuario_actual = usuario_actual
        self.session = SessionLocal()
        self._aviso_duplicados_mostrado = False
        self._build_ui()
        self._cargar()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        hdr = QHBoxLayout()
        lbl = QLabel("Gestión de Usuarios")
        lbl.setObjectName("subtitle")
        hdr.addWidget(lbl)
        hdr.addStretch()

        btn_nuevo = QPushButton("+ Nuevo Usuario")
        btn_nuevo.setObjectName("btn_primary")
        btn_nuevo.clicked.connect(self._nuevo)
        hdr.addWidget(btn_nuevo)
        lay.addLayout(hdr)

        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels(
            ["ID", "Usuario", "Nombre completo", "Rol", "Código QR", "Estado"]
        )
        self.tabla.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.doubleClicked.connect(self._editar)
        lay.addWidget(self.tabla, 1)

        btn_row = QHBoxLayout()
        btn_ed = QPushButton("✏ Editar")
        btn_ed.clicked.connect(self._editar)
        btn_row.addWidget(btn_ed)
        btn_row.addStretch()
        lay.addLayout(btn_row)

    def _cargar(self):
        self._advertir_duplicados()
        usuarios = self.session.query(Usuario).all()
        self.tabla.setRowCount(len(usuarios))
        for i, u in enumerate(usuarios):
            tiene_qr = bool(u.qr_imagen and resolver_ruta(u.qr_imagen))
            qr_txt = "🟢 Configurado" if tiene_qr else "⚪ Sin QR"
            vals = [
                str(u.id),
                u.username,
                u.nombre_completo,
                u.rol_display,
                qr_txt,
                "✓ Activo" if u.activo else "✗ Inactivo",
            ]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 4 and tiene_qr:
                    it.setForeground(Qt.green)
                self.tabla.setItem(i, j, it)
            self.tabla.item(i, 0).setData(Qt.UserRole, u.id)

    def _advertir_duplicados(self):
        """Informa una sola vez si ya existen usernames equivalentes en la BD."""
        if self._aviso_duplicados_mostrado:
            return
        duplicados = detectar_duplicados_username(self.session)
        if not duplicados:
            return

        self._aviso_duplicados_mostrado = True
        detalle = "\n".join(
            " · ".join(f"'{u.username}' (ID {u.id})" for u in usuarios)
            for usuarios in duplicados.values()
        )
        QMessageBox.warning(
            self,
            "Usuarios duplicados detectados",
            "Se encontraron nombres de usuario que solo difieren en mayúsculas/minúsculas:\n\n"
            f"{detalle}\n\n"
            "No se eliminó ni fusionó ningún registro. Corrija los nombres desde esta "
            "pantalla para evitar inicios de sesión ambiguos.",
        )

    def _nuevo(self):
        dlg = UsuarioDialog(self.session, parent=self)
        if dlg.exec():
            self._cargar()

    def _editar(self):
        row = self.tabla.currentRow()
        if row < 0:
            return
        uid = self.tabla.item(row, 0).data(Qt.UserRole)
        u = self.session.get(Usuario, uid)
        if u:
            dlg = UsuarioDialog(self.session, u, parent=self)
            if dlg.exec():
                self._cargar()

    def closeEvent(self, event):
        self.session.close()
        super().closeEvent(event)
