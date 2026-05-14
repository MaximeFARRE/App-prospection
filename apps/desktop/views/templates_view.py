from __future__ import annotations

import re
from pathlib import Path
from typing import Union

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.config import settings


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES_DIR = _PROJECT_ROOT / "data" / "templates"

_STEPS    = ("intro", "followup_1", "followup_2")
_LANGUAGES = ("fr", "en")
_VARIANTS  = ("a", "b", "c", "d")

_VAR_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")

_VARIABLES = [
    ("{{civilite}}",      "Civilité (Monsieur / Madame / Mr. / Ms.)"),
    ("{{first_name}}",    "Prénom du contact"),
    ("{{last_name}}",     "Nom du contact"),
    ("{{full_name}}",     "Prénom + Nom"),
    ("{{company}}",       "Entreprise"),
    ("{{job_title}}",     "Poste"),
    ("{{sender_name}}",   "Votre nom"),
    ("{{sender_email}}",  "Votre adresse email"),
    ("{{sender_website}}","Votre site web"),
]


# ── Focus tracker ─────────────────────────────────────────────────────────────

class _FocusTracker(QObject):
    """Écoute les événements FocusIn sur plusieurs widgets et émet focused(widget)."""

    focused: pyqtSignal = pyqtSignal(object)

    def __init__(self, targets: list[QWidget], parent: QObject | None = None) -> None:
        super().__init__(parent)
        for target in targets:
            target.installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.FocusIn:
            self.focused.emit(obj)
        return False


# ── Vue principale ────────────────────────────────────────────────────────────

class TemplatesView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        _TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        self._current_file: Path | None = None
        self._focused_editor: Union[QLineEdit, QTextEdit, None] = None
        self._build_ui()
        self._refresh_list()

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_list_panel())
        root.addWidget(self._build_editor_panel(), stretch=1)

    def _build_list_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(250)
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setStyleSheet(
            "QFrame { background: #f8fafc; border-right: 1px solid #e2e8f0; }"
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Templates")
        title.setStyleSheet("color: #0f172a; font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { border: 1px solid #e2e8f0; border-radius: 6px; background: #ffffff; color: #0f172a; }"
            "QListWidget::item { padding: 6px 8px; color: #0f172a; }"
            "QListWidget::item:selected { background: #dbeafe; color: #1e40af; }"
        )
        self._list.currentItemChanged.connect(self._on_template_selected)
        layout.addWidget(self._list, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._new_btn = QPushButton("+ Nouveau")
        self._new_btn.clicked.connect(self._new_template)
        btn_row.addWidget(self._new_btn)

        self._duplicate_btn = QPushButton("Dupliquer")
        self._duplicate_btn.setEnabled(False)
        self._duplicate_btn.clicked.connect(self._duplicate_template)
        btn_row.addWidget(self._duplicate_btn)

        self._delete_btn = QPushButton("Supprimer")
        self._delete_btn.setEnabled(False)
        self._delete_btn.setStyleSheet(
            "QPushButton:enabled { color: #dc2626; } QPushButton:disabled { color: #94a3b8; }"
        )
        self._delete_btn.clicked.connect(self._delete_template)
        btn_row.addWidget(self._delete_btn)

        layout.addLayout(btn_row)
        return panel

    def _build_editor_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # ── Métadonnées ───────────────────────────────────────────────────────
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)

        meta_row.addWidget(QLabel("Étape :"))
        self._step_combo = QComboBox()
        for step in _STEPS:
            self._step_combo.addItem(step, step)
        meta_row.addWidget(self._step_combo)

        meta_row.addWidget(QLabel("Langue :"))
        self._lang_combo = QComboBox()
        for lang in _LANGUAGES:
            self._lang_combo.addItem(lang.upper(), lang)
        meta_row.addWidget(self._lang_combo)

        meta_row.addWidget(QLabel("Variante :"))
        self._variant_combo = QComboBox()
        for v in _VARIANTS:
            self._variant_combo.addItem(v, v)
        meta_row.addWidget(self._variant_combo)

        meta_row.addStretch(1)
        layout.addLayout(meta_row)

        # ── Sujet ─────────────────────────────────────────────────────────────
        subject_row = QHBoxLayout()
        subject_row.setSpacing(8)
        subject_row.addWidget(QLabel("Sujet :"))
        self._subject_input = QLineEdit()
        self._subject_input.setPlaceholderText("Objet de l'email (ex. : Stage Finance/Data – disponible dès maintenant)")
        subject_row.addWidget(self._subject_input)
        layout.addLayout(subject_row)

        # ── Barre variables ───────────────────────────────────────────────────
        var_label = QLabel("Insérer une variable (cliquer insère à la position du curseur) :")
        var_label.setStyleSheet("color: #475569; font-size: 11px;")
        layout.addWidget(var_label)

        var_row = QHBoxLayout()
        var_row.setSpacing(4)
        var_row.setContentsMargins(0, 0, 0, 0)
        for var_text, var_tooltip in _VARIABLES:
            btn = QPushButton(var_text)
            btn.setToolTip(var_tooltip)
            btn.setFixedHeight(26)
            btn.setStyleSheet(
                "QPushButton { background: #e2e8f0; border: none; border-radius: 4px; "
                "font-size: 11px; padding: 0 6px; color: #1e293b; }"
                "QPushButton:hover { background: #bfdbfe; color: #1e40af; }"
            )
            btn.clicked.connect(lambda _, v=var_text: self._insert_variable(v))
            var_row.addWidget(btn)
        var_row.addStretch(1)
        layout.addLayout(var_row)

        # ── Corps ─────────────────────────────────────────────────────────────
        body_label = QLabel("Corps du message :")
        body_label.setStyleSheet("font-weight: 600; color: #0f172a;")
        layout.addWidget(body_label)

        self._body_editor = QTextEdit()
        self._body_editor.setPlaceholderText(
            "Rédigez le corps de l'email ici...\n\n"
            "• Une ligne vide entre deux blocs de texte crée un nouveau paragraphe dans l'email.\n"
            "• Utilisez les boutons ci-dessus pour insérer des variables ({{first_name}}, etc.)."
        )
        self._body_editor.setAcceptRichText(False)
        layout.addWidget(self._body_editor, stretch=1)

        # ── Suivi du focus ────────────────────────────────────────────────────
        self._focused_editor = self._body_editor
        self._tracker = _FocusTracker([self._subject_input, self._body_editor], self)
        self._tracker.focused.connect(self._on_editor_focused)

        # ── Actions ───────────────────────────────────────────────────────────
        actions_row = QHBoxLayout()
        self._preview_btn = QPushButton("Aperçu")
        self._preview_btn.setToolTip("Afficher un rendu avec des données d'exemple")
        self._preview_btn.clicked.connect(self._show_preview)
        actions_row.addWidget(self._preview_btn)

        actions_row.addStretch(1)

        self._save_btn = QPushButton("Enregistrer")
        self._save_btn.setStyleSheet(
            "QPushButton { background: #3b82f6; color: white; font-weight: 600; "
            "padding: 6px 20px; border-radius: 4px; }"
            "QPushButton:hover { background: #2563eb; }"
        )
        self._save_btn.clicked.connect(self._save_template)
        actions_row.addWidget(self._save_btn)

        layout.addLayout(actions_row)
        return panel

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_editor_focused(self, widget: object) -> None:
        if isinstance(widget, (QLineEdit, QTextEdit)):
            self._focused_editor = widget

    def _insert_variable(self, variable: str) -> None:
        if isinstance(self._focused_editor, QLineEdit):
            pos = self._focused_editor.cursorPosition()
            text = self._focused_editor.text()
            self._focused_editor.setText(text[:pos] + variable + text[pos:])
            self._focused_editor.setCursorPosition(pos + len(variable))
            self._focused_editor.setFocus()
        elif isinstance(self._focused_editor, QTextEdit):
            self._focused_editor.insertPlainText(variable)
            self._focused_editor.setFocus()

    def _refresh_list(self) -> None:
        selected_path = self._current_file
        self._list.blockSignals(True)
        self._list.clear()
        for f in sorted(_TEMPLATES_DIR.glob("*.md")):
            item = QListWidgetItem(_display_name(f.stem))
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            self._list.addItem(item)
        self._list.blockSignals(False)

        # Restaurer la sélection
        if selected_path is not None:
            for i in range(self._list.count()):
                item = self._list.item(i)
                if item and Path(item.data(Qt.ItemDataRole.UserRole)) == selected_path:
                    self._list.setCurrentItem(item)
                    return
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _on_template_selected(self, item: QListWidgetItem | None) -> None:
        if item is None:
            self._current_file = None
            self._delete_btn.setEnabled(False)
            self._duplicate_btn.setEnabled(False)
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        self._current_file = path
        self._delete_btn.setEnabled(True)
        self._duplicate_btn.setEnabled(True)
        self._load_template_file(path)

    def _load_template_file(self, path: Path) -> None:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Erreur", f"Impossible de lire le template :\n{exc}")
            return

        lines = raw.splitlines()
        subject = ""
        body_start = 0

        if lines and lines[0].strip().lower().startswith("subject:"):
            subject = lines[0].split(":", 1)[1].strip()
            body_start = 1
            if len(lines) > 1 and not lines[1].strip():
                body_start = 2

        body = "\n".join(lines[body_start:]).strip()
        self._subject_input.setText(subject)
        self._body_editor.setPlainText(body)

        # Synchroniser les combos avec le nom de fichier
        stem = path.stem  # e.g. "followup_1_fr_a"
        parts = stem.split("_")
        if len(parts) >= 3:
            variant = parts[-1]
            lang = parts[-2]
            step = "_".join(parts[:-2])
            _set_combo(self._step_combo, step)
            _set_combo(self._lang_combo, lang)
            _set_combo(self._variant_combo, variant)

    def _new_template(self) -> None:
        self._list.clearSelection()
        self._current_file = None
        self._delete_btn.setEnabled(False)
        self._subject_input.clear()
        self._body_editor.clear()
        self._step_combo.setCurrentIndex(0)
        self._lang_combo.setCurrentIndex(0)
        self._variant_combo.setCurrentIndex(0)
        self._subject_input.setFocus()

    def _save_template(self) -> None:
        subject = self._subject_input.text().strip()
        body = self._body_editor.toPlainText().strip()

        if not subject:
            QMessageBox.warning(self, "Enregistrer", "Le sujet ne peut pas être vide.")
            self._subject_input.setFocus()
            return
        if not body:
            QMessageBox.warning(self, "Enregistrer", "Le corps du message ne peut pas être vide.")
            self._body_editor.setFocus()
            return

        step    = self._step_combo.currentData()
        lang    = self._lang_combo.currentData()
        variant = self._variant_combo.currentData()
        target  = _TEMPLATES_DIR / f"{step}_{lang}_{variant}.md"

        if target.exists() and target != self._current_file:
            answer = QMessageBox.question(
                self,
                "Écraser ?",
                f"Le fichier {target.name} existe déjà. L'écraser ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        content = f"Subject: {subject}\n\n{body}\n"
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer le fichier :\n{exc}")
            return

        self._current_file = target
        self._refresh_list()
        QMessageBox.information(self, "Enregistré", f"Template enregistré : {target.name}")

    def _delete_template(self) -> None:
        if self._current_file is None:
            return
        answer = QMessageBox.question(
            self,
            "Supprimer",
            f"Supprimer définitivement {self._current_file.name} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._current_file.unlink()
        except OSError as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le fichier :\n{exc}")
            return
        self._current_file = None
        self._delete_btn.setEnabled(False)
        self._refresh_list()
        self._new_template()

    def _duplicate_template(self) -> None:
        if self._current_file is None:
            return

        source_name = self._current_file.stem
        stem_parts = source_name.split("_")
        if len(stem_parts) >= 3:
            src_variant = stem_parts[-1]
            src_lang    = stem_parts[-2]
            src_step    = "_".join(stem_parts[:-2])
        else:
            src_step    = self._step_combo.currentData()
            src_lang    = self._lang_combo.currentData()
            src_variant = self._variant_combo.currentData()

        next_variant = _find_next_variant(src_step, src_lang, src_variant)

        # Charger le contenu source dans l'éditeur
        self._load_template_file(self._current_file)

        # Désélectionner le fichier source (mode "nouveau")
        self._list.clearSelection()
        self._current_file = None
        self._delete_btn.setEnabled(False)
        self._duplicate_btn.setEnabled(False)

        # Configurer les combos sur la nouvelle variante
        _set_combo(self._step_combo, src_step)
        _set_combo(self._lang_combo, src_lang)
        _set_combo(self._variant_combo, next_variant)

        # Mettre à jour le titre de la fenêtre pour indiquer la copie
        self._status_label_copy_hint = f"Nouveau template (depuis copie de {source_name})"

    def _show_preview(self) -> None:
        subject = self._subject_input.text().strip()
        body    = self._body_editor.toPlainText().strip()
        if not subject and not body:
            QMessageBox.information(self, "Aperçu", "Le template est vide.")
            return

        preview_vars  = _build_preview_vars()
        rend_subject  = _replace_vars(subject, preview_vars)
        rend_body     = _replace_vars(body, preview_vars)

        dialog = QDialog(self)
        dialog.setWindowTitle("Aperçu du template (données fictives)")
        dialog.setMinimumSize(680, 500)
        layout = QVBoxLayout(dialog)

        note = QLabel("Rendu avec des données d'exemple — les vraies valeurs sont insérées à l'envoi.")
        note.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(note)

        subject_box = QLabel(f"<b>Sujet :</b> {rend_subject}")
        subject_box.setStyleSheet(
            "background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px;"
        )
        subject_box.setWordWrap(True)
        layout.addWidget(subject_box)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #e2e8f0;")
        layout.addWidget(sep)

        body_display = QTextEdit()
        body_display.setReadOnly(True)
        body_display.setPlainText(rend_body)
        layout.addWidget(body_display, stretch=1)

        # Highlight any unreplaced {{variable}} in a warning
        remaining = re.findall(r"{{[^}]+}}", rend_subject + " " + rend_body)
        if remaining:
            warn = QLabel(f"⚠ Variables non reconnues : {', '.join(set(remaining))}")
            warn.setStyleSheet("color: #b45309; font-size: 11px;")
            layout.addWidget(warn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _display_name(stem: str) -> str:
    """Transforme 'followup_1_fr_a' en 'followup_1  ·  FR  ·  variante a'."""
    parts = stem.split("_")
    if len(parts) >= 3:
        variant = parts[-1]
        lang    = parts[-2].upper()
        step    = "_".join(parts[:-2])
        return f"{step}  ·  {lang}  ·  variante {variant}"
    return stem


def _find_next_variant(step: str, lang: str, source_variant: str) -> str:
    """Retourne la première lettre de variante non utilisée pour step+lang."""
    existing = {f.stem.split("_")[-1] for f in _TEMPLATES_DIR.glob(f"{step}_{lang}_*.md")}
    for candidate in _VARIANTS:
        if candidate not in existing:
            return candidate
    # Toutes les variantes prédéfinies sont prises : incrémenter depuis la source
    if source_variant and len(source_variant) == 1:
        next_char = chr(ord(source_variant) + 1)
        if next_char not in existing:
            return next_char
    return _VARIANTS[-1]


def _set_combo(combo: QComboBox, value: str) -> None:
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            combo.setCurrentIndex(i)
            return


def _build_preview_vars() -> dict[str, str]:
    sender_name    = getattr(settings, "sender_name", "") or "Votre Nom"
    sender_website = getattr(settings, "sender_website", "") or "votresite.com"
    return {
        "first_name":     "Jean",
        "last_name":      "Dupont",
        "full_name":      "Jean Dupont",
        "company":        "Acme Corp",
        "job_title":      "Directeur",
        "sex":            "homme",
        "sexe":           "homme",
        "civilite":       "Monsieur",
        "sender_name":    sender_name,
        "sender_email":   "expediteur@gmail.com",
        "sender_website": sender_website,
    }


def _replace_vars(text: str, variables: dict[str, str]) -> str:
    def _sub(match: re.Match[str]) -> str:
        return variables.get(match.group(1).strip(), match.group(0))
    return _VAR_PATTERN.sub(_sub, text)
