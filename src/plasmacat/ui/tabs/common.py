"""Small shared widgets for the Control Center tabs."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget


def need_bar(value: float) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setTextVisible(False)
    bar.setFixedHeight(10)
    set_need(bar, value)
    return bar


def set_need(bar: QProgressBar, value: float) -> None:
    v = int(min(max(value, 0), 100))
    bar.setValue(v)
    color = "#5ac85a" if v > 50 else "#e6b43c" if v > 25 else "#dc5046"
    bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
                      "QProgressBar { border-radius: 4px; }")


def reset_row(on_reset, text: str = "Reset to defaults") -> tuple[QWidget, QPushButton]:
    """A right-aligned 'Reset to defaults' button row (every tab has one)."""
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addStretch(1)
    btn = QPushButton(text)
    btn.clicked.connect(on_reset)
    lay.addWidget(btn)
    return row, btn


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: palette(placeholder-text);")
    return lbl
