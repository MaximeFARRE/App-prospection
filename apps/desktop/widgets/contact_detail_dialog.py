from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout, QWidget


class ContactDetailDialog(QDialog):
    def __init__(self, contact: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Détail du contact")
        self.setMinimumWidth(520)

        company = getattr(contact, "company", None)
        company_name = company.name if company else "-"

        layout = QVBoxLayout(self)
        form = QFormLayout()

        fields = [
            ("Prénom", contact.first_name),
            ("Nom", contact.last_name),
            ("Entreprise", company_name),
            ("Poste", contact.job_title),
            ("Email", contact.email),
            ("Pays", contact.country),
            ("Ville", contact.city),
            ("Téléphone", contact.phone),
            ("LinkedIn", contact.linkedin_url),
            ("Statut email", contact.email_status),
            ("Bloqué", "Oui" if contact.is_blocked else "Non"),
            ("Source", contact.source),
            ("Notes", contact.notes),
        ]

        for label_text, value in fields:
            value_label = QLabel(_display(value))
            value_label.setWordWrap(True)
            form.addRow(label_text, value_label)

        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def _display(value: Any) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text if text else "-"

