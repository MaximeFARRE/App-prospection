from __future__ import annotations

import re

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class CampaignPreviewDialog(QDialog):
    def __init__(self, subject: str, body: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prévisualisation de l'email")
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        subject_label = QLabel(f"Sujet : {subject}")
        subject_label.setWordWrap(True)
        subject_label.setTextInteractionFlags(subject_label.textInteractionFlags())
        layout.addWidget(subject_label)

        if _looks_like_html(body):
            body_widget = QTextBrowser()
            body_widget.setHtml(body)
        else:
            body_widget = QPlainTextEdit()
            body_widget.setPlainText(body)
            body_widget.setReadOnly(True)
        layout.addWidget(body_widget, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)


def _looks_like_html(text: str) -> bool:
    return bool(re.search(r"<[a-zA-Z][^>]*>", text))

