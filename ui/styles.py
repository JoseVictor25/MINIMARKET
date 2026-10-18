"""
ui/styles.py - Paleta de colores y hoja de estilos Qt para todo el sistema.
Tema oscuro profesional - Slate and Teal.
"""
from pathlib import Path

_CHECK_ICON_PATH = str(Path(__file__).resolve().parent.parent / "assets" / "check_white.png").replace("\\", "/")

PALETTE = {
    "bg_base":      "#111827",
    "bg_surface":   "#1f2937",
    "bg_card":      "#263040",
    "bg_input":     "#1a2333",
    "bg_hover":     "#2d3f55",
    "border":       "#334155",
    "accent":       "#0ea5e9",
    "accent_hover": "#38bdf8",
    "accent_dark":  "#0284c7",
    "pos_center":           "#E2E8F0",
    "pos_center_text":      "#f1f5f9",
    "pos_table_bg":         "#ffffff",
    "pos_table_alt":        "#f8fafc",
    "pos_table_text":       "#111827",
    "pos_table_header_bg":  "#0f172a",
    "pos_table_header_text":"#0ea5e9",
    "success":       "#10b981",
    "danger":        "#f43f5e",
    "warning":       "#f59e0b",
    "text_primary":  "#f1f5f9",
    "text_secondary":"#94a3b8",
    "text_muted":    "#64748b",
    "white":         "#ffffff",
}

STYLESHEET = f"""
QMainWindow, QDialog, QWidget {{
    background-color: {PALETTE['bg_base']};
    color: {PALETTE['text_primary']};
    font-family: 'Segoe UI', 'Arial', sans-serif;
    font-size: 13px;
}}
QFrame#card {{
    background-color: {PALETTE['bg_card']};
    border: 1px solid {PALETTE['border']};
    border-radius: 10px;
    padding: 10px;
}}
QLabel {{
    color: {PALETTE['text_primary']};
    background: transparent;
}}
QLabel#title {{
    font-size: 20px;
    font-weight: bold;
    color: {PALETTE['white']};
}}
QLabel#subtitle {{
    font-size: 16px;
    font-weight: bold;
    color: {PALETTE['accent']};
    padding: 2px 0;
}}
QLabel#label_small {{
    font-size: 11px;
    color: {PALETTE['text_secondary']};
}}
QLabel#total_amount {{
    font-size: 28px;
    font-weight: bold;
    color: {PALETTE['success']};
}}
QLabel#stock_bajo {{
    color: {PALETTE['warning']};
    font-weight: bold;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {{
    background-color: {PALETTE['bg_input']};
    border: 1px solid {PALETTE['border']};
    border-radius: 7px;
    padding: 7px 11px;
    color: {PALETTE['text_primary']};
    selection-background-color: {PALETTE['accent']};
    min-height: 30px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QTextEdit:focus {{
    border: 2px solid {PALETTE['accent']};
    background-color: {PALETTE['bg_hover']};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover,
QComboBox:hover {{
    border-color: #4a6a8a;
}}
QLineEdit#barcode_input {{
    font-size: 16px;
    font-weight: bold;
    border: 2px solid {PALETTE['accent']};
    padding: 8px 12px;
    border-radius: 8px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid {PALETTE['border']};
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
    background-color: {PALETTE['bg_input']};
}}
QComboBox::down-arrow {{
    image: url(assets/combo_arrow.png);
    width: 12px;
    height: 12px;
}}
QComboBox QAbstractItemView {{
    background-color: {PALETTE['bg_card']};
    border: 1.5px solid {PALETTE['accent']};
    border-radius: 8px;
    selection-background-color: {PALETTE['accent']};
    selection-color: #ffffff;
    color: {PALETTE['text_primary']};
    padding: 6px;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    min-height: 34px;
    padding: 6px 12px;
    border-radius: 6px;
    margin: 2px 0px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {PALETTE['bg_hover']};
    color: {PALETTE['accent_hover']};
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {PALETTE['accent']};
    color: #ffffff;
    font-weight: bold;
}}
QPushButton {{
    background-color: {PALETTE['bg_hover']};
    color: {PALETTE['text_primary']};
    border: 1px solid {PALETTE['border']};
    border-radius: 7px;
    padding: 7px 18px;
    font-weight: 600;
    font-size: 13px;
    min-height: 32px;
}}
QPushButton:hover {{
    background-color: {PALETTE['accent']};
    color: {PALETTE['white']};
    border-color: {PALETTE['accent']};
}}
QPushButton:pressed {{
    background-color: {PALETTE['accent_dark']};
    color: {PALETTE['white']};
}}
QPushButton:disabled {{
    background-color: {PALETTE['bg_surface']};
    color: {PALETTE['text_muted']};
    border-color: {PALETTE['border']};
}}
QPushButton#btn_primary {{
    background-color: {PALETTE['accent']};
    color: {PALETTE['white']};
    border: none;
    font-size: 13px;
    font-weight: bold;
    min-height: 36px;
    border-radius: 8px;
    padding: 7px 20px;
}}
QPushButton#btn_primary:hover {{
    background-color: {PALETTE['accent_hover']};
    color: {PALETTE['white']};
}}
QPushButton#btn_primary:pressed {{
    background-color: {PALETTE['accent_dark']};
    color: {PALETTE['white']};
}}
QPushButton#btn_success {{
    background-color: {PALETTE['success']};
    color: {PALETTE['white']};
    border: none;
    font-size: 13px;
    min-height: 36px;
    border-radius: 8px;
    font-weight: bold;
    padding: 7px 20px;
}}
QPushButton#btn_success:hover {{
    background-color: #059669;
    color: {PALETTE['white']};
}}
QPushButton#btn_success:pressed {{
    background-color: #047857;
    color: {PALETTE['white']};
}}
QPushButton#btn_danger {{
    background-color: {PALETTE['danger']};
    color: {PALETTE['white']};
    border: none;
    border-radius: 7px;
    padding: 7px 18px;
    font-weight: bold;
    min-height: 32px;
}}
QPushButton#btn_danger:hover {{
    background-color: #e11d48;
    color: {PALETTE['white']};
}}
QPushButton#btn_danger:pressed {{
    background-color: #be123c;
    color: {PALETTE['white']};
}}
QPushButton#btn_warning {{
    background-color: {PALETTE['warning']};
    color: #1c1917;
    border: none;
    border-radius: 7px;
    padding: 7px 18px;
    font-weight: bold;
    min-height: 32px;
}}
QPushButton#btn_warning:hover {{
    background-color: #d97706;
    color: #1c1917;
}}
QPushButton#btn_warning:pressed {{
    background-color: #b45309;
    color: {PALETTE['white']};
}}
QPushButton#btn_fkey {{
    background-color: {PALETTE['bg_card']};
    color: {PALETTE['accent']};
    border: 1px solid {PALETTE['border']};
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: bold;
    min-height: 28px;
    min-width: 70px;
}}
QPushButton#btn_fkey:hover {{
    background-color: {PALETTE['accent']};
    color: {PALETTE['white']};
    border-color: {PALETTE['accent']};
}}
QTableWidget {{
    background-color: {PALETTE['bg_surface']};
    gridline-color: {PALETTE['border']};
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
    alternate-background-color: {PALETTE['bg_card']};
    selection-background-color: #1e4976;
    selection-color: {PALETTE['white']};
    font-size: 13px;
}}
QTableWidget::item {{
    padding: 7px 10px;
    border: none;
}}
QTableWidget::item:selected {{
    background-color: #1e4976;
    color: {PALETTE['white']};
}}
QHeaderView::section {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #1e293b, stop:1 #16202e);
    color: #ffffff;
    border: none;
    border-right: 1px solid #334155;
    border-bottom: 2.5px solid {PALETTE['accent']};
    padding: 8px 8px;
    font-weight: bold;
    font-size: 13px;
    letter-spacing: 0.3px;
}}
QHeaderView::section:hover {{
    background: #253347;
    color: {PALETTE['accent_hover']};
}}
QListWidget#sidebar {{
    background-color: {PALETTE['bg_surface']};
    border: none;
    border-right: 1px solid {PALETTE['border']};
    outline: none;
}}
QListWidget#sidebar::item {{
    color: {PALETTE['text_secondary']};
    padding: 13px 20px;
    border-radius: 0;
    font-size: 13px;
    font-weight: 500;
}}
QListWidget#sidebar::item:selected {{
    background-color: rgba(14, 165, 233, 0.18);
    color: {PALETTE['accent']};
    border-left: 3px solid {PALETTE['accent']};
    font-weight: bold;
}}
QListWidget#sidebar::item:hover:!selected {{
    background-color: rgba(255,255,255,0.05);
    color: {PALETTE['text_primary']};
}}
QScrollBar:vertical {{
    background: {PALETTE['bg_surface']};
    width: 7px;
    border-radius: 4px;
    margin: 2px 0;
}}
QScrollBar::handle:vertical {{
    background: #475569;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {PALETTE['accent']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {PALETTE['bg_surface']};
    height: 7px;
    border-radius: 4px;
    margin: 0 2px;
}}
QScrollBar::handle:horizontal {{
    background: #475569;
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {PALETTE['accent']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QLabel#alert_danger {{
    background-color: rgba(244,63,94,0.12);
    border: 1px solid {PALETTE['danger']};
    border-radius: 6px;
    color: #fb7185;
    padding: 7px 14px;
    font-weight: bold;
}}
QLabel#alert_success {{
    background-color: rgba(16,185,129,0.12);
    border: 1px solid {PALETTE['success']};
    border-radius: 6px;
    color: #34d399;
    padding: 7px 14px;
    font-weight: bold;
}}
QLabel#alert_warning {{
    background-color: rgba(245,158,11,0.12);
    border: 1px solid {PALETTE['warning']};
    border-radius: 6px;
    color: #fbbf24;
    padding: 7px 14px;
    font-weight: bold;
}}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {PALETTE['border']};
}}
QTabWidget::pane {{
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
    background: {PALETTE['bg_surface']};
    top: -1px;
}}
QTabBar::tab {{
    background: #1e293b;
    color: #94a3b8;
    padding: 10px 24px;
    min-width: 145px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border: 1px solid {PALETTE['border']};
    margin-right: 4px;
    font-size: 13px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #0284c7, stop:1 #0369a1);
    color: #ffffff;
    font-weight: bold;
    border: 1.5px solid #38bdf8;
    border-bottom: none;
}}
QTabBar::tab:hover:!selected {{
    background: {PALETTE['bg_hover']};
    color: #ffffff;
    border-color: #475569;
}}
QStatusBar {{
    background-color: {PALETTE['bg_surface']};
    color: {PALETTE['text_secondary']};
    border-top: 1px solid {PALETTE['border']};
    font-size: 12px;
    padding: 2px 4px;
}}
QCheckBox {{
    spacing: 8px;
    color: {PALETTE['text_primary']};
    font-size: 13px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid {PALETTE['border']};
    background-color: {PALETTE['bg_input']};
}}
QCheckBox::indicator:hover {{
    border-color: {PALETTE['accent']};
}}
QCheckBox::indicator:checked {{
    background-color: {PALETTE['accent']};
    border-color: {PALETTE['accent']};
    image: url("{_CHECK_ICON_PATH}");
}}
QGroupBox {{
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
    margin-top: 18px;
    padding-top: 10px;
    color: {PALETTE['accent']};
    font-weight: bold;
    font-size: 13px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    left: 12px;
    background: {PALETTE['bg_base']};
}}
QSplitter::handle {{
    background: {PALETTE['border']};
    width: 1px;
    height: 1px;
}}
QMessageBox {{
    background-color: {PALETTE['bg_surface']};
}}
QMessageBox QLabel {{
    color: {PALETTE['text_primary']};
    font-size: 13px;
}}
QToolTip {{
    background-color: {PALETTE['bg_card']};
    color: {PALETTE['text_primary']};
    border: 1px solid {PALETTE['border']};
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 12px;
}}
/* QDateEdit */
QDateEdit {{
    background-color: {PALETTE['bg_input']};
    border: 1px solid {PALETTE['border']};
    border-radius: 7px;
    padding: 6px 10px;
    color: {PALETTE['text_primary']};
    font-size: 13px;
    font-weight: 500;
    min-height: 28px;
    min-width: 115px;
}}
QDateEdit:hover {{
    border-color: {PALETTE['accent_hover']};
}}
QDateEdit:focus {{
    border: 2px solid {PALETTE['accent']};
    background-color: {PALETTE['bg_hover']};
}}
QDateEdit::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid {PALETTE['border']};
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
    background-color: {PALETTE['bg_card']};
}}
QDateEdit::drop-down:hover {{
    background-color: {PALETTE['bg_hover']};
}}
QDateEdit::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {PALETTE['accent']};
    width: 0;
    height: 0;
}}

/* QCalendarWidget */
QCalendarWidget {{
    background-color: #0f172a;
    border: 1.5px solid #334155;
    border-radius: 8px;
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: #1e293b;
    border-bottom: 1.5px solid #334155;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    min-height: 38px;
}}
QCalendarWidget QToolButton {{
    color: #ffffff;
    background-color: transparent;
    border: none;
    border-radius: 6px;
    font-size: 16px;
    font-weight: bold;
    padding: 2px 8px;
}}
QCalendarWidget QToolButton:hover {{
    background-color: #334155;
    color: #38bdf8;
}}
QCalendarWidget QToolButton:pressed {{
    background-color: #0ea5e9;
    color: #ffffff;
}}
QCalendarWidget QSpinBox {{
    background-color: #1e293b;
    color: #ffffff;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 13px;
    font-weight: bold;
}}
QCalendarWidget QTableView {{
    background-color: #0f172a;
    alternate-background-color: #0f172a;
    border: none;
    outline: none;
    selection-background-color: #0ea5e9;
    selection-color: #ffffff;
}}
QCalendarWidget QTableView::item {{
    color: #f1f5f9;
    font-size: 13px;
    border-radius: 6px;
    padding: 3px;
    margin: 1px;
}}
QCalendarWidget QTableView::item:hover {{
    background-color: #1e293b;
    color: #38bdf8;
}}
QCalendarWidget QTableView::item:selected {{
    background-color: #0ea5e9;
    color: #ffffff;
    font-weight: bold;
}}
QCalendarWidget QHeaderView {{
    background-color: #1e293b;
    border: none;
}}
QCalendarWidget QHeaderView::section {{
    background-color: #1e293b;
    color: #94a3b8;
    border: none;
    border-bottom: 1.5px solid #334155;
    padding: 6px 0px;
    font-size: 11px;
    font-weight: bold;
}}
"""

CALENDAR_POPUP_STYLESHEET = """
QCalendarWidget {
    background-color: #111827;
    border: 1.5px solid #2e3e55;
    border-radius: 12px;
}
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background-color: #111827;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    border-bottom: 1px solid #1f293d;
    min-height: 42px;
}
QCalendarWidget QToolButton {
    color: #ffffff;
    background-color: transparent;
    border: none;
    border-radius: 6px;
    font-size: 15px;
    font-weight: bold;
    padding: 2px 8px;
}
QCalendarWidget QToolButton:hover {
    background-color: #1e293b;
    color: #38bdf8;
}
QCalendarWidget QToolButton#qt_calendar_prevmonth,
QCalendarWidget QToolButton#qt_calendar_nextmonth {
    font-size: 20px;
    font-weight: 300;
    qproperty-icon: none;
    width: 28px;
    height: 28px;
}
QCalendarWidget QSpinBox {
    background-color: #111827;
    color: #ffffff;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 14px;
    font-weight: bold;
}
QCalendarWidget QTableView {
    background-color: #111827;
    border: none;
    outline: none;
    selection-background-color: transparent;
}
"""

_UPPER_DAYS = {0: 'LUN', 1: 'MAR', 2: 'MIÉ', 3: 'JUE', 4: 'VIE', 5: 'SÁB', 6: 'DOM'}


def _crear_delegate_calendario():
    from PyQt5.QtWidgets import QStyledItemDelegate, QStyle
    from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QPainterPath
    from PyQt5.QtCore import Qt, QRectF

    class _ElegantCalendarDelegate(QStyledItemDelegate):
        def paint(self, painter, option, index):
            r = index.row()
            c = index.column()
            rect = option.rect

            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)

            # Fila 0: Encabezados en mayúsculas (LUN, MAR, MIÉ, JUE, VIE, SÁB, DOM)
            if r == 0:
                painter.fillRect(rect, QColor('#111827'))
                painter.setFont(QFont('Segoe UI', 9, QFont.Bold))
                if c >= 5:  # Sáb, Dom
                    painter.setPen(QColor('#60a5fa'))
                else:
                    painter.setPen(QColor('#94a3b8'))
                text = _UPPER_DAYS.get(c, '')
                painter.drawText(rect, Qt.AlignCenter, text)
                painter.restore()
                return

            # Días del mes (Filas 1 a 6)
            text = str(index.data() or '')
            is_selected = bool(option.state & QStyle.State_Selected)
            is_hover = bool(option.state & QStyle.State_MouseOver)
            is_weekend = (c >= 5)

            if is_selected:
                # Cápsula azul con borde cyan como el diseño de referencia
                pill_rect = QRectF(rect.x() + 3, rect.y() + 3, rect.width() - 6, rect.height() - 6)
                path = QPainterPath()
                path.addRoundedRect(pill_rect, 9, 9)
                painter.fillPath(path, QColor('#0284c7'))
                painter.setPen(QPen(QColor('#38bdf8'), 1.8))
                painter.drawPath(path)

                painter.setFont(QFont('Segoe UI', 11, QFont.Bold))
                painter.setPen(QColor('#ffffff'))
                painter.drawText(rect, Qt.AlignCenter, text)
            else:
                if is_hover:
                    pill_rect = QRectF(rect.x() + 3, rect.y() + 3, rect.width() - 6, rect.height() - 6)
                    path = QPainterPath()
                    path.addRoundedRect(pill_rect, 7, 7)
                    painter.fillPath(path, QColor('#1e293b'))

                painter.setFont(QFont('Segoe UI', 10, QFont.Normal))

                is_outside = False
                try:
                    day_num = int(text)
                    if r == 1 and day_num > 20:
                        is_outside = True
                    elif r >= 5 and day_num < 15:
                        is_outside = True
                except ValueError:
                    pass

                if is_outside:
                    painter.setPen(QColor('#475569'))
                elif is_weekend:
                    painter.setPen(QColor('#60a5fa'))
                    painter.setFont(QFont('Segoe UI', 10, QFont.DemiBold))
                else:
                    painter.setPen(QColor('#f8fafc'))

                painter.drawText(rect, Qt.AlignCenter, text)

            painter.restore()

    return _ElegantCalendarDelegate


def configurar_calendario_elegante(widget):
    """
    Aplica diseño oscuro moderno y elegante a un QDateEdit o QCalendarWidget exactamente
    como el diseño de referencia:
    - Encabezados en mayúsculas (LUN, MAR, MIÉ, JUE, VIE, SÁB, DOM)
    - Cápsula redondeada cyan/azul para el día seleccionado
    - Flechas de navegación limpias (‹ / ›)
    - Sin columnas de semanas y con paleta de contrastes suave y agradable.
    """
    from PyQt5.QtWidgets import QCalendarWidget, QDateEdit, QToolButton, QTableView
    from PyQt5.QtGui import QIcon

    if isinstance(widget, QDateEdit):
        widget.setCalendarPopup(True)
        cal = widget.calendarWidget()
        widget._cal_ref = cal
    elif isinstance(widget, QCalendarWidget):
        cal = widget
    else:
        return

    if not cal:
        return

    cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
    cal.setStyleSheet(CALENDAR_POPUP_STYLESHEET)

    tv = cal.findChild(QTableView)
    if tv:
        delegate_cls = _crear_delegate_calendario()
        cal._elegant_delegate = delegate_cls(tv)
        if isinstance(widget, QDateEdit):
            widget._elegant_delegate = cal._elegant_delegate
        tv.setItemDelegate(cal._elegant_delegate)

    # Botones anterior y siguiente sin iconos nativos de Windows
    prev_btn = cal.findChild(QToolButton, "qt_calendar_prevmonth")
    next_btn = cal.findChild(QToolButton, "qt_calendar_nextmonth")
    if prev_btn:
        prev_btn.setIcon(QIcon())
        prev_btn.setText("‹")
        prev_btn.setToolTip("Mes anterior")
    if next_btn:
        next_btn.setIcon(QIcon())
        next_btn.setText("›")
        next_btn.setToolTip("Mes siguiente")


