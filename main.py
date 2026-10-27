"""
main.py – Punto de entrada del sistema Mini Market POS.

Flujo:
  1. Inicializa la base de datos (crea tablas + datos semilla si es nueva).
  2. Muestra el diálogo de login.
  3. Si el login es exitoso, abre la ventana principal.
"""
import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

from database import init_db
from ui.styles import STYLESHEET
from ui.login_dialog import LoginDialog
from ui.main_window import MainWindow


def main():
    # ── Inicializar base de datos ─────────────────────────────────────────────
    init_db()

    # ── Crear aplicación Qt ───────────────────────────────────────────────────
    app = QApplication(sys.argv)
    app.setApplicationName("Mini Market POS")
    app.setApplicationVersion("1.0.0")
    app.setQuitOnLastWindowClosed(False)

    # Tipografía global
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Hoja de estilos global (tema oscuro)
    app.setStyleSheet(STYLESHEET)

    import argparse
    parser = argparse.ArgumentParser(description="Mini Market POS")
    parser.add_argument("--user", help="Iniciar sesión automáticamente con el usuario indicado")
    parser.add_argument("--rol", choices=["admin", "cajero"], help="Iniciar sesión automáticamente con el rol indicado")
    args, _ = parser.parse_known_args()

    auto_usuario = None
    if args.user or args.rol:
        from database import SessionLocal
        from models.usuario import Usuario
        from services.usuario_service import usuario_unico_por_username
        s = SessionLocal()
        try:
            if args.user:
                # Mismo criterio que el login: no distingue mayúsculas/minúsculas.
                # Si el username es ambiguo, no se auto-inicia sesión.
                auto_usuario = usuario_unico_por_username(s, args.user)
            elif args.rol:
                auto_usuario = s.query(Usuario).filter_by(rol=args.rol, activo=True).first()
            if auto_usuario:
                s.expunge(auto_usuario)
        finally:
            s.close()

    # ── Bucle de Sesiones (Permite cerrar sesión y volver a iniciar) ───────────
    while True:
        if auto_usuario:
            usuario = auto_usuario
            auto_usuario = None  # Si cierra sesión manualmente, mostrará el LoginDialog normal
        else:
            login = LoginDialog()
            if login.exec() != LoginDialog.Accepted:
                # Si el usuario cancela o cierra la ventana de login, se sale de la app
                break

            usuario = login.usuario_autenticado
            if not usuario:
                break

        # Abrir ventana principal con el usuario autenticado, siempre maximizada
        ventana = MainWindow(usuario)
        ventana.showMaximized()

        # Esperar a que la ventana principal termine su ciclo
        app.exec_()

        # Si no se solicitó cerrar sesión (ej. se cerró por la 'X'), salir del sistema
        if not getattr(ventana, "solicito_cerrar_sesion", False):
            break

    sys.exit(0)


if __name__ == "__main__":
    main()
