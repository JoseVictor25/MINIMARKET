"""
ui/login_dialog.py – Pantalla de inicio de sesión Peke Market.
Diseño moderno réplica exacta del mockup oficial.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QSize
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QWidget,
)

from database import SessionLocal
from models.usuario import Usuario
from config import (
    APP_NAME, SLOGAN, SLOGAN_COLOR, BRAND_COLOR, BRAND_TEXT_COLOR,
    get_brand_hover, get_brand_dark, get_brand_text_color,
    LOGIN_BTN_TEXT, LOGIN_SUBTITLE,
)


def _tint_icon(pixmap: QPixmap, color_hex: str) -> QPixmap:
    """Tinta un icono al color corporativo de la marca."""
    if pixmap.isNull():
        return pixmap
    tinted = QPixmap(pixmap.size())
    tinted.fill(Qt.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(color_hex))
    painter.end()
    return tinted


# ── Paleta corporativa centralizada ──────────────────────────────────────────
_BRAND_COLOR = BRAND_COLOR
_BRAND_HOVER = get_brand_hover(_BRAND_COLOR)
_BRAND_DARK  = get_brand_dark(_BRAND_COLOR)
_TEXT_COLOR  = get_brand_text_color(_BRAND_COLOR, BRAND_TEXT_COLOR)

_INPUT_STYLE = f"""
    QLineEdit {{
        background-color: #161f2c;
        border: 1.5px solid #2e3b4e;
        border-radius: 12px;
        padding: 11px 16px;
        color: #f8fafc;
        font-size: 14px;
        selection-background-color: {_BRAND_COLOR};
    }}
    QLineEdit:focus {{
        border: 2px solid {_BRAND_COLOR};
        background-color: #192332;
    }}
    QLineEdit:hover {{
        border-color: #3f516b;
    }}
"""

_PASS_INPUT_STYLE = f"""
    QLineEdit {{
        background-color: #161f2c;
        border: 1.5px solid #2e3b4e;
        border-radius: 12px;
        padding: 11px 48px 11px 16px;
        color: #f8fafc;
        font-size: 14px;
        selection-background-color: {_BRAND_COLOR};
    }}
    QLineEdit:focus {{
        border: 2px solid {_BRAND_COLOR};
        background-color: #192332;
    }}
    QLineEdit:hover {{
        border-color: #3f516b;
    }}
"""


class LoginDialog(QDialog):
    """Diálogo modal de autenticación personalizado según la identidad de marca."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.usuario_autenticado: Usuario | None = None
        self._build_ui()
        self.setWindowTitle(f"{APP_NAME} – Iniciar Sesión")
        h = 550 if SLOGAN else 520
        self.setFixedSize(400, h)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Fondo exterior ─────────────────────────────────────────────────────
        self.setStyleSheet("background-color: #0d121c; border-radius: 20px;")

        # ── Card central con gradiente sutil y borde redondeado ───────────────
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #222b3b, stop:1 #161e2b);
                border-radius: 20px;
                border: 1px solid #2a374a;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(0)

        # ── Logo oficial ──────────────────────────────────────────────
        lbl_logo = QLabel()
        lbl_logo.setAlignment(Qt.AlignCenter)
        lbl_logo.setStyleSheet("background: transparent; border: none;")

        logo_candidatos = [
            Path("assets/logo.png"), Path("assets/logo_mockup.png"),
            Path("assets/logo.jpg"), Path("logo.png"), Path("logo.jpg"),
        ]
        logo_cargado = False
        for p in logo_candidatos:
            if p.is_file():
                pix = QPixmap(str(p))
                if not pix.isNull():
                    lbl_logo.setPixmap(pix.scaled(220, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    layout.addWidget(lbl_logo)
                    logo_cargado = True
                    break

        if not logo_cargado:
            lbl_fallback = QLabel(APP_NAME)
            lbl_fallback.setAlignment(Qt.AlignCenter)
            lbl_fallback.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {_BRAND_COLOR}; background: transparent;")
            layout.addWidget(lbl_fallback)

        # ── Lema opcional si está configurado ──────────────────────────
        if SLOGAN:
            layout.addSpacing(10)
            lbl_slogan = QLabel(SLOGAN)
            lbl_slogan.setAlignment(Qt.AlignCenter)
            lbl_slogan.setStyleSheet(f"""
                color: {SLOGAN_COLOR};
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 2px;
                background: transparent;
                border: none;
            """)
            layout.addWidget(lbl_slogan)

        layout.addSpacing(14 if SLOGAN else 16)

        # ── Subtítulo ──────────────────────────────────────────────────
        lbl_sub = QLabel(LOGIN_SUBTITLE)
        lbl_sub.setAlignment(Qt.AlignCenter)
        lbl_sub.setStyleSheet("""
            color: #8492a6;
            font-size: 13px;
            background: transparent;
            border: none;
        """)
        layout.addWidget(lbl_sub)

        layout.addSpacing(22)

        # ── Campo Usuario ──────────────────────────────────────────────
        h_u = QHBoxLayout()
        h_u.setSpacing(8)
        lbl_u_icon = QLabel()
        lbl_u_icon.setStyleSheet("background: transparent; border: none;")
        u_icon_path = Path("assets/user_icon_crisp.png")
        if not u_icon_path.is_file():
            u_icon_path = Path("assets/user_icon_clean.png")
        if u_icon_path.is_file():
            lbl_u_icon.setPixmap(_tint_icon(QPixmap(str(u_icon_path)), _BRAND_COLOR).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            lbl_u_icon.setText("👤")
            lbl_u_icon.setStyleSheet(f"color: {_BRAND_COLOR}; font-size: 13px; background: transparent; border: none;")
        h_u.addWidget(lbl_u_icon)

        lbl_u_txt = QLabel("USUARIO")
        lbl_u_txt.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: bold; letter-spacing: 1.2px; background: transparent; border: none;")
        h_u.addWidget(lbl_u_txt)
        h_u.addStretch()

        layout.addLayout(h_u)
        layout.addSpacing(8)

        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Ingrese su nombre de usuario")
        self.input_user.setObjectName("login_input")
        self.input_user.setFixedHeight(48)
        self.input_user.setStyleSheet(_INPUT_STYLE)
        layout.addWidget(self.input_user)

        layout.addSpacing(18)

        # ── Campo Contraseña ───────────────────────────────────────────
        h_p = QHBoxLayout()
        h_p.setSpacing(8)
        lbl_p_icon = QLabel()
        lbl_p_icon.setStyleSheet("background: transparent; border: none;")
        p_icon_path = Path("assets/lock_icon_crisp.png")
        if not p_icon_path.is_file():
            p_icon_path = Path("assets/lock_icon_clean.png")
        if p_icon_path.is_file():
            lbl_p_icon.setPixmap(_tint_icon(QPixmap(str(p_icon_path)), _BRAND_COLOR).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            lbl_p_icon.setText("🔒")
            lbl_p_icon.setStyleSheet(f"color: {_BRAND_COLOR}; font-size: 13px; background: transparent; border: none;")
        h_p.addWidget(lbl_p_icon)

        lbl_p_txt = QLabel("CONTRASEÑA")
        lbl_p_txt.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: bold; letter-spacing: 1.2px; background: transparent; border: none;")
        h_p.addWidget(lbl_p_txt)
        h_p.addStretch()

        layout.addLayout(h_p)
        layout.addSpacing(8)

        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_pass.setPlaceholderText("Ingrese su contraseña")
        self.input_pass.setFixedHeight(48)
        self.input_pass.setStyleSheet(_PASS_INPUT_STYLE)

        # Botón para mostrar / ocultar contraseña
        pass_layout = QHBoxLayout(self.input_pass)
        pass_layout.setContentsMargins(0, 0, 10, 0)
        pass_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pass_layout.addStretch()

        self.btn_toggle_pass = QPushButton()
        self.btn_toggle_pass.setFocusPolicy(Qt.NoFocus)
        self.btn_toggle_pass.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_pass.setFixedSize(30, 30)
        self.btn_toggle_pass.setToolTip("Mostrar / Ocultar contraseña")

        eye_gray_path = Path("assets/eye_crisp_gray.png")
        eye_pink_path = Path("assets/eye_crisp_slash_pink.png")
        if eye_gray_path.is_file():
            self._icon_eye_open = QIcon(str(eye_gray_path))
            if eye_pink_path.is_file() and _BRAND_COLOR == "#bf1e61":
                self._icon_eye_active = QIcon(str(eye_pink_path))
            else:
                self._icon_eye_active = QIcon(_tint_icon(QPixmap(str(eye_gray_path)), _BRAND_COLOR))
            self.btn_toggle_pass.setIcon(self._icon_eye_open)
            self.btn_toggle_pass.setIconSize(QSize(20, 20))
            self.btn_toggle_pass.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    outline: none;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.08);
                    border-radius: 15px;
                }
            """)
        else:
            self._icon_eye_open = None
            self._icon_eye_active = None
            self.btn_toggle_pass.setText("👁")
            self.btn_toggle_pass.setStyleSheet("QPushButton { background: transparent; border: none; outline: none; font-size: 16px; color: #8492a6; }")

        self.btn_toggle_pass.clicked.connect(self._toggle_password_visibility)
        pass_layout.addWidget(self.btn_toggle_pass)

        layout.addWidget(self.input_pass)

        layout.addSpacing(8)

        # ── Mensaje de error ──────────────────────────────────────────
        self.lbl_error = QLabel("")
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setStyleSheet(f"color: {_BRAND_COLOR}; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)

        layout.addSpacing(18)

        # ── Botón Ingresar ────────────────────────────────────────────
        btn = QPushButton(LOGIN_BTN_TEXT)
        btn.setObjectName("btn_primary")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(48)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_BRAND_COLOR};
                color: {_TEXT_COLOR};
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background-color: {_BRAND_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {_BRAND_DARK};
            }}
        """)
        btn.clicked.connect(self._on_login)
        layout.addWidget(btn)

        root.addWidget(card)

        # ── Conexiones ────────────────────────────────────────────────────────
        self.input_pass.returnPressed.connect(self._on_login)
        self.input_user.returnPressed.connect(self.input_pass.setFocus)
        self.input_user.setFocus()

    def _toggle_password_visibility(self):
        if self.input_pass.echoMode() == QLineEdit.Password:
            self.input_pass.setEchoMode(QLineEdit.Normal)
            if self._icon_eye_active:
                self.btn_toggle_pass.setIcon(self._icon_eye_active)
            else:
                self.btn_toggle_pass.setText("🙈")
                self.btn_toggle_pass.setStyleSheet(f"QPushButton {{ background: transparent; border: none; outline: none; font-size: 16px; color: {_BRAND_COLOR}; }}")
        else:
            self.input_pass.setEchoMode(QLineEdit.Password)
            if self._icon_eye_open:
                self.btn_toggle_pass.setIcon(self._icon_eye_open)
            else:
                self.btn_toggle_pass.setText("👁")
                self.btn_toggle_pass.setStyleSheet("QPushButton { background: transparent; border: none; outline: none; font-size: 16px; color: #8492a6; }")

    # ── Lógica ────────────────────────────────────────────────────────────────
    def _on_login(self):
        username = self.input_user.text().strip()
        password = self.input_pass.text()

        if not username or not password:
            self._show_error("⚠  Complete usuario y contraseña.")
            self._shake()
            return

        session = SessionLocal()
        try:
            usuario = session.query(Usuario).filter_by(username=username, activo=True).first()
            if usuario and usuario.verificar_password(password):
                self.usuario_autenticado = usuario
                session.expunge(usuario)
                self.accept()
            else:
                self._show_error("✖  Usuario o contraseña incorrectos.")
                self.input_pass.clear()
                self.input_pass.setFocus()
                self._shake()
        finally:
            session.close()

    def _show_error(self, msg: str):
        self.lbl_error.setText(msg)
        self.lbl_error.show()

    def _shake(self):
        """Animación de sacudida cuando las credenciales son incorrectas."""
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        pos = self.pos()
        anim.setKeyValueAt(0,    pos)
        anim.setKeyValueAt(0.15, pos + QPoint(-10, 0))
        anim.setKeyValueAt(0.30, pos + QPoint(10, 0))
        anim.setKeyValueAt(0.45, pos + QPoint(-8, 0))
        anim.setKeyValueAt(0.60, pos + QPoint(8, 0))
        anim.setKeyValueAt(0.75, pos + QPoint(-4, 0))
        anim.setKeyValueAt(0.90, pos + QPoint(4, 0))
        anim.setKeyValueAt(1.0,  pos)
        anim.start()
        self._anim = anim  # evitar que el GC destruya la animación
