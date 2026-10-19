"""Application-wide QSS stylesheet derived from the user's color palette."""

from __future__ import annotations
from . import colors as C


def build_stylesheet(accent_gold: str = None, accent_rust: str = None,
                     font_size: int = 14,
                     font_family: str = "AppCJK") -> str:
    gold = accent_gold or C.ACCENT_GOLD
    rust = accent_rust or C.ACCENT_RUST

    return f"""
    /* ===== Global ===== */
    QWidget {{
        background-color: {C.BG_BASE};
        color: {C.TEXT_PRIMARY};
        font-size: {font_size}px;
        font-family: "{font_family}";
        outline: 0;
    }}
    QMainWindow {{
        background-color: {C.BG_BASE};
    }}

    /* ===== Tooltip ===== */
    QToolTip {{
        background-color: {C.BG_PANEL};
        color: {C.TEXT_PRIMARY};
        border: 1px solid {C.BORDER};
        padding: 6px 10px;
        border-radius: 6px;
        font-size: {font_size - 1}px;
    }}

    /* ===== Buttons (rounded pill, dark style) ===== */
    QPushButton {{
        background-color: {C.BG_PANEL};
        color: {C.TEXT_PRIMARY};
        border: 1px solid {C.BORDER};
        border-radius: 14px;
        padding: 8px 18px;
        font-size: {font_size}px;
    }}
    QPushButton:hover {{
        background-color: {C.BG_PANEL_HOVER};
        border: 1px solid {C.DIVIDER_STRONG};
    }}
    QPushButton:pressed {{
        background-color: {C.BG_PANEL_PRESSED};
    }}
    QPushButton:disabled {{
        color: {C.TEXT_DISABLED};
        background-color: {C.BG_BASE};
        border: 1px solid {C.DIVIDER};
    }}
    QPushButton[accent="gold"] {{
        background-color: {gold};
        color: {C.TEXT_INVERT};
        border: 1px solid {gold};
    }}
    QPushButton[accent="gold"]:hover {{
        background-color: #E0B58A;
    }}
    QPushButton[accent="gold"]:pressed {{
        background-color: #C99870;
    }}
    QPushButton[accent="rust"] {{
        background-color: {rust};
        color: {C.TEXT_PRIMARY};
        border: 1px solid {rust};
    }}
    QPushButton[accent="ghost"] {{
        background-color: transparent;
        border: 1px solid transparent;
    }}
    QPushButton[accent="ghost"]:hover {{
        background-color: {C.BG_PANEL_HOVER};
    }}
    QPushButton[accent="danger"] {{
        background-color: transparent;
        color: {C.ERROR};
        border: 1px solid {C.BORDER};
        padding: 0px;
    }}
    QPushButton[accent="icon"] {{
        background-color: transparent;
        color: {C.TEXT_SECONDARY};
        border: 1px solid {C.BORDER};
        border-radius: 14px;
        padding: 0px;
        font-size: 14px;
    }}
    QPushButton[accent="icon"]:hover {{
        background-color: {C.BG_PANEL_HOVER};
        color: {C.TEXT_PRIMARY};
        border: 1px solid {C.DIVIDER_STRONG};
    }}
    QPushButton[accent="icon"]:pressed {{
        background-color: {C.BG_PANEL_PRESSED};
    }}
    QPushButton[accent="compact"] {{
        background-color: {C.BG_PANEL};
        color: {C.TEXT_PRIMARY};
        border: 1px solid {C.BORDER};
        border-radius: 8px;
        padding: 4px 12px;
        font-size: 13px;
    }}
    QPushButton[accent="compact"]:hover {{
        background-color: {C.BG_PANEL_HOVER};
    }}
    QPushButton[accent="compact"]:pressed {{
        background-color: {C.BG_PANEL_PRESSED};
    }}
    QPushButton[accent="danger"]:hover {{
        background-color: rgba(201, 72, 75, 30);
    }}
    QPushButton[accent="success"] {{
        background-color: transparent;
        color: {C.SUCCESS};
        border: 1px solid {C.BORDER};
    }}
    QPushButton[accent="success"]:hover {{
        background-color: rgba(127, 176, 105, 30);
    }}

    /* ===== Inputs ===== */
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {C.BG_INPUT};
        color: {C.TEXT_PRIMARY};
        border: 1px solid {C.BORDER};
        border-radius: 8px;
        padding: 6px 10px;
        selection-background-color: {C.SELECTION_BG};
        selection-color: {C.TEXT_PRIMARY};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {gold};
    }}
    QComboBox::drop-down {{
        border: 0;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {C.BG_PANEL};
        border: 1px solid {C.BORDER};
        selection-background-color: {C.SELECTION_BG};
        outline: 0;
    }}
    QComboBox::down-arrow {{
        image: none;
        width: 0; height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 6px solid {C.TEXT_SECONDARY};
    }}

    /* ===== Lists / Trees / Tables ===== */
    QListWidget, QTreeWidget, QTreeView, QTableWidget, QTableView {{
        background-color: {C.BG_BASE};
        alternate-background-color: {C.BG_PANEL};
        color: {C.TEXT_PRIMARY};
        border: 1px solid {C.BORDER};
        border-radius: 8px;
        outline: 0;
    }}
    QListWidget::item, QTreeWidget::item {{
        padding: 8px 12px;
        border-radius: 6px;
    }}
    QListWidget::item:selected, QTreeWidget::item:selected {{
        background-color: {C.SELECTION_BG};
        color: {C.TEXT_PRIMARY};
    }}
    QListWidget::item:hover, QTreeWidget::item:hover {{
        background-color: {C.BG_PANEL_HOVER};
    }}
    QHeaderView::section {{
        background-color: {C.BG_PANEL};
        color: {C.TEXT_SECONDARY};
        border: 0;
        border-bottom: 1px solid {C.DIVIDER};
        padding: 8px 12px;
    }}

    /* ===== Scrollbars (slim) ===== */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {C.BG_PANEL_PRESSED};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {C.DIVIDER_STRONG};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {C.BG_PANEL_PRESSED};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ===== Menu ===== */
    QMenu {{
        background-color: {C.BG_PANEL};
        color: {C.TEXT_PRIMARY};
        border: 1px solid {C.BORDER};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 6px 18px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: {C.SELECTION_BG};
    }}
    QMenu::separator {{
        height: 1px;
        background: {C.DIVIDER};
        margin: 4px 6px;
    }}

    /* ===== Slider ===== */
    QSlider::groove:horizontal {{
        background: {C.BG_PANEL_PRESSED};
        height: 4px;
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {gold};
        border-radius: 2px;
    }}
    QSlider::add-page:horizontal {{
        background: {C.BG_PANEL_PRESSED};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {gold};
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }}


    /* ===== Radio button ===== */
    QRadioButton {{
        spacing: 8px;
        color: {C.TEXT_PRIMARY};
    }}
    QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 9px;
        background: {C.BG_INPUT};
        border: 1px solid {C.BORDER};
    }}
    QRadioButton::indicator:hover {{
        border: 1px solid {gold};
    }}
    QRadioButton::indicator:checked {{
        background: {gold};
        border: 1px solid {gold};
    }}
    QRadioButton:disabled {{
        color: {C.TEXT_DISABLED};
    }}

    /* ===== Checkbox ===== */
    QCheckBox {{
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        background: {C.BG_INPUT};
        border: 1px solid {C.BORDER};
    }}
    QCheckBox::indicator:checked {{
        background: {gold};
        border: 1px solid {gold};
    }}
    QCheckBox::indicator:hover {{
        border: 1px solid {gold};
    }}

    /* ===== Progress ===== */
    QProgressBar {{
        background: {C.BG_PANEL};
        border: 0;
        border-radius: 4px;
        text-align: center;
        color: {C.TEXT_PRIMARY};
    }}
    QProgressBar::chunk {{
        background: {gold};
        border-radius: 4px;
    }}

    /* ===== Splitter ===== */
    QSplitter::handle {{ background: {C.DIVIDER}; }}

    /* ===== Tab ===== */
    QTabWidget::pane {{
        border: 1px solid {C.BORDER};
        border-radius: 8px;
        background: {C.BG_BASE};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {C.TEXT_SECONDARY};
        padding: 8px 16px;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {gold};
        border-bottom: 2px solid {gold};
    }}
    QTabBar::tab:hover:!selected {{
        color: {C.TEXT_PRIMARY};
    }}

    /* ===== Status bar ===== */
    QStatusBar {{
        background: {C.BG_PANEL};
        color: {C.TEXT_SECONDARY};
        border-top: 1px solid {C.DIVIDER};
    }}

    /* ===== Scroll area ===== */
    QScrollArea {{ background: transparent; border: 0; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    """
