from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


@dataclass(slots=True)
class ManualContactPayload:
    first_name: str | None
    last_name: str | None
    email: str
    company_name: str | None
    job_title: str | None
    sex: str | None
    country: str | None
    city: str | None
    phone: str | None
    linkedin_url: str | None
    notes: str | None
    contact_id: int | None = None


class ManualContactDialog(QDialog):
    """Dialogue d'ajout ou de modification d'un contact.

    En mode ajout (contact=None) : tous les champs sont vides et modifiables.
    En mode édition (contact=<objet ORM>) : champs pré-remplis, email en lecture seule.
    """

    def __init__(self, parent: QWidget | None = None, *, contact: Any = None) -> None:
        super().__init__(parent)
        self._contact_id: int | None = getattr(contact, "id", None)
        self._edit_mode = contact is not None

        self.setWindowTitle("Modifier le contact" if self._edit_mode else "Ajouter un contact")
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._first_name_input = QLineEdit()
        self._first_name_input.setPlaceholderText("Prénom")
        form.addRow("Prénom", self._first_name_input)

        self._last_name_input = QLineEdit()
        self._last_name_input.setPlaceholderText("Nom")
        form.addRow("Nom", self._last_name_input)

        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("email@entreprise.com")
        if self._edit_mode:
            self._email_input.setReadOnly(True)
            self._email_input.setToolTip("L'adresse email ne peut pas être modifiée.")
            self._email_input.setStyleSheet("background: #f1f5f9; color: #64748b;")
        form.addRow("Email *", self._email_input)

        self._company_input = QLineEdit()
        self._company_input.setPlaceholderText("Entreprise")
        form.addRow("Entreprise", self._company_input)

        self._job_title_input = QLineEdit()
        self._job_title_input.setPlaceholderText("Poste")
        form.addRow("Poste", self._job_title_input)

        self._sex_input = QComboBox()
        self._sex_input.addItem("-", "")
        self._sex_input.addItem("homme", "homme")
        self._sex_input.addItem("femme", "femme")
        form.addRow("Sexe", self._sex_input)

        self._country_input = QLineEdit()
        self._country_input.setPlaceholderText("Pays")
        form.addRow("Pays", self._country_input)

        self._city_input = QLineEdit()
        self._city_input.setPlaceholderText("Ville")
        form.addRow("Ville", self._city_input)

        self._phone_input = QLineEdit()
        self._phone_input.setPlaceholderText("Téléphone")
        form.addRow("Téléphone", self._phone_input)

        self._linkedin_input = QLineEdit()
        self._linkedin_input.setPlaceholderText("https://linkedin.com/in/...")
        form.addRow("LinkedIn", self._linkedin_input)

        self._notes_input = QTextEdit()
        self._notes_input.setPlaceholderText("Notes")
        self._notes_input.setFixedHeight(90)
        form.addRow("Notes", self._notes_input)

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.accepted.connect(self._on_submit)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if contact is not None:
            self._prefill(contact)

    def _prefill(self, contact: Any) -> None:
        if contact.first_name:
            self._first_name_input.setText(contact.first_name)
        if contact.last_name:
            self._last_name_input.setText(contact.last_name)
        if contact.email:
            self._email_input.setText(contact.email)

        company = getattr(contact, "company", None)
        if company and company.name:
            self._company_input.setText(company.name)

        if contact.job_title:
            self._job_title_input.setText(contact.job_title)

        sex = contact.sex or ""
        if sex == "homme":
            self._sex_input.setCurrentIndex(1)
        elif sex == "femme":
            self._sex_input.setCurrentIndex(2)
        else:
            self._sex_input.setCurrentIndex(0)

        if contact.country:
            self._country_input.setText(contact.country)
        if contact.city:
            self._city_input.setText(contact.city)
        if contact.phone:
            self._phone_input.setText(contact.phone)
        if contact.linkedin_url:
            self._linkedin_input.setText(contact.linkedin_url)
        if contact.notes:
            self._notes_input.setPlainText(contact.notes)

    def payload(self) -> ManualContactPayload:
        return ManualContactPayload(
            first_name=_clean(self._first_name_input.text()),
            last_name=_clean(self._last_name_input.text()),
            email=self._email_input.text().strip(),
            company_name=_clean(self._company_input.text()),
            job_title=_clean(self._job_title_input.text()),
            sex=_clean(str(self._sex_input.currentData() or "")),
            country=_clean(self._country_input.text()),
            city=_clean(self._city_input.text()),
            phone=_clean(self._phone_input.text()),
            linkedin_url=_clean(self._linkedin_input.text()),
            notes=_clean(self._notes_input.toPlainText()),
            contact_id=self._contact_id,
        )

    def _on_submit(self) -> None:
        if not self._edit_mode:
            email = self._email_input.text().strip()
            if not email:
                QMessageBox.warning(self, "Contact", "Le champ email est obligatoire.")
                self._email_input.setFocus()
                return
        self.accept()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None
