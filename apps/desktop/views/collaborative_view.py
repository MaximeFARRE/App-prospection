"""Onglet base collaborative — crédits, déblocage et import de contacts."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.collaborative_service import TIER_RANGES, compute_unlockable
from services.settings_service import get_collaborative_config, save_collaborative_config
from workers.collaborative_workers import (
    BulkContributeWorker,
    FetchStatsWorker,
    ImportUnlockedWorker,
    SyncCreditsWorker,
    UnlockContactsWorker,
)


class CollaborativeView(QWidget):
    """Vue principale du mode collaboratif.

    Affiche les crédits, permet de débloquer des contacts et de les importer
    dans la base locale.
    """

    credits_updated = pyqtSignal(int)

    def __init__(self) -> None:
        super().__init__()
        self._credits_worker: SyncCreditsWorker | None = None
        self._stats_worker: FetchStatsWorker | None = None
        self._unlock_worker: UnlockContactsWorker | None = None
        self._import_worker: ImportUnlockedWorker | None = None
        self._bulk_worker: BulkContributeWorker | None = None
        self._bulk_sample_worker: BulkContributeWorker | None = None
        self._build_ui()

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        content = QVBoxLayout(container)
        content.setContentsMargins(16, 16, 16, 16)
        content.setSpacing(12)

        title = QLabel("Base collaborative")
        title.setStyleSheet("color: #f1f5f9; font-size: 24px; font-weight: 700;")
        content.addWidget(title)

        content.addWidget(self._build_stats_section())
        content.addWidget(self._build_credits_section())
        content.addWidget(self._build_contribute_section())
        content.addWidget(self._build_actions_section())
        content.addWidget(self._build_contacts_table())
        content.addStretch(1)

        scroll.setWidget(container)
        root.addWidget(scroll)

    def _build_contribute_section(self) -> QGroupBox:
        group = QGroupBox("Contribuer mes contacts")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        desc = QLabel(
            "Partage tes contacts locaux avec la base collaborative. "
            "Seuls les contacts non encore partagés et suffisamment qualifiés sont envoyés."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        self._contribute_btn = QPushButton("Contribuer mes contacts")
        self._contribute_btn.setFixedWidth(200)
        self._contribute_btn.clicked.connect(self._bulk_contribute)
        btn_row.addWidget(self._contribute_btn)

        self._contribute_sample_btn = QPushButton("Contribuer 10 contacts")
        self._contribute_sample_btn.setFixedWidth(170)
        self._contribute_sample_btn.setToolTip("Envoie uniquement les 10 premiers contacts non encore partagés")
        self._contribute_sample_btn.clicked.connect(self._bulk_contribute_sample)
        btn_row.addWidget(self._contribute_sample_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._contribute_progress = QProgressBar()
        self._contribute_progress.setRange(0, 1)
        self._contribute_progress.setValue(0)
        self._contribute_progress.setFormat("%v / %m contacts traités")
        self._contribute_progress.setVisible(False)
        layout.addWidget(self._contribute_progress)

        self._contribute_status = QLabel("")
        self._contribute_status.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(self._contribute_status)

        return group

    def _build_stats_section(self) -> QGroupBox:
        group = QGroupBox("Statistiques de la base")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # ── Ligne 1 : 3 cartes métriques ──────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)

        self._stat_total = self._make_stat_card("Contacts dans la base", "—")
        self._stat_unlocked = self._make_stat_card("Débloqués par moi", "—")
        self._stat_contributed = self._make_stat_card("Partagés par moi", "—")

        cards_row.addWidget(self._stat_total[0])
        cards_row.addWidget(self._stat_unlocked[0])
        cards_row.addWidget(self._stat_contributed[0])
        outer.addLayout(cards_row)

        # ── Ligne 2 : top 3 contributeurs ─────────────────────────────────────
        top_group = QGroupBox("Top 3 contributeurs")
        top_group.setStyleSheet("QGroupBox { font-size: 12px; color: #cbd5e1; }")
        top_layout = QHBoxLayout(top_group)
        top_layout.setContentsMargins(12, 8, 12, 8)
        top_layout.setSpacing(16)

        medals = ["🥇", "🥈", "🥉"]
        self._top_labels: list[QLabel] = []
        for medal in medals:
            lbl = QLabel(f"{medal}  —")
            lbl.setStyleSheet("font-size: 13px; color: #e2e8f0;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            top_layout.addWidget(lbl)
            self._top_labels.append(lbl)

        top_layout.addStretch()

        refresh_stats_btn = QPushButton("↻")
        refresh_stats_btn.setFixedWidth(32)
        refresh_stats_btn.setToolTip("Rafraîchir les statistiques")
        refresh_stats_btn.clicked.connect(self._fetch_stats)
        top_layout.addWidget(refresh_stats_btn)

        outer.addWidget(top_group)
        return group

    @staticmethod
    def _make_stat_card(title: str, value: str) -> tuple[QWidget, QLabel]:
        """Retourne (widget_carte, label_valeur) pour une métrique."""
        card = QWidget()
        card.setStyleSheet(
            "QWidget { background: #1e293b; border: 1px solid #334155;"
            " border-radius: 8px; }"
        )
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            "font-size: 26px; font-weight: 700; color: #f1f5f9;"
            " border: none; background: transparent;"
        )
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "font-size: 11px; color: #94a3b8; border: none; background: transparent;"
        )
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setWordWrap(True)

        layout.addWidget(val_lbl)
        layout.addWidget(title_lbl)
        return card, val_lbl

    def _build_credits_section(self) -> QGroupBox:
        group = QGroupBox("Crédits & paliers")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        # ── En-tête : prochain palier + badge accès complet ───────────────────
        header_row = QHBoxLayout()
        self._next_tier_label = QLabel("Prochain palier : 5 contributions → +5 contacts par contribution")
        self._next_tier_label.setStyleSheet("color: #e2e8f0; font-size: 12px; font-weight: 600;")
        header_row.addWidget(self._next_tier_label)
        header_row.addStretch()
        self._full_access_badge = QLabel("★ Accès complet")
        self._full_access_badge.setStyleSheet(
            "color: #fff; background: #16a34a; padding: 2px 10px;"
            " border-radius: 10px; font-size: 11px; font-weight: 700;"
        )
        self._full_access_badge.setVisible(False)
        header_row.addWidget(self._full_access_badge)
        layout.addLayout(header_row)

        # ── Barre de progression inter-palier ─────────────────────────────────
        self._tier_bar = QProgressBar()
        self._tier_bar.setRange(0, 5)
        self._tier_bar.setValue(0)
        self._tier_bar.setFormat("%v / %m contributions")
        self._tier_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._tier_bar.setFixedHeight(18)
        layout.addWidget(self._tier_bar)

        # ── Contacts débloquables ─────────────────────────────────────────────
        credits_row = QHBoxLayout()
        self._credits_label = QLabel("5 contacts débloquables")
        self._credits_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        credits_row.addWidget(self._credits_label)
        credits_row.addStretch()
        refresh_btn = QPushButton("↻ Rafraîchir")
        refresh_btn.setFixedWidth(110)
        refresh_btn.clicked.connect(self._sync_credits)
        credits_row.addWidget(refresh_btn)
        layout.addLayout(credits_row)

        # ── Roadmap des paliers ───────────────────────────────────────────────
        roadmap_row = QHBoxLayout()
        roadmap_row.setSpacing(4)
        self._tier_chips: list[QLabel] = []
        milestones = [
            ("5",   "+25 contacts"),
            ("10",  "+100 contacts"),
            ("20",  "+200 contacts"),
            ("50",  "+500 contacts"),
            ("100", "Accès complet"),
        ]
        for i, (threshold, reward) in enumerate(milestones):
            chip = QLabel(f"{threshold} ▸ {reward}")
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setFixedHeight(26)
            chip.setStyleSheet(self._chip_style("future"))
            chip.setToolTip(f"À {threshold} contributions : {reward}")
            roadmap_row.addWidget(chip)
            self._tier_chips.append(chip)
            if i < len(milestones) - 1:
                sep = QLabel("›")
                sep.setStyleSheet("color: #475569; font-size: 14px;")
                sep.setFixedWidth(12)
                sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
                roadmap_row.addWidget(sep)
        layout.addLayout(roadmap_row)

        return group

    @staticmethod
    def _chip_style(state: str) -> str:
        """Retourne le style CSS d'un chip de palier selon son état (thème sombre)."""
        if state == "done":
            return (
                "background: #166534; color: #bbf7d0; border: 1px solid #22c55e;"
                " border-radius: 6px; padding: 0 8px; font-size: 11px; font-weight: 600;"
            )
        if state == "current":
            return (
                "background: #1e3a8a; color: #bfdbfe; border: 1px solid #3b82f6;"
                " border-radius: 6px; padding: 0 8px; font-size: 11px; font-weight: 700;"
            )
        return (  # future
            "background: #1e293b; color: #64748b; border: 1px solid #334155;"
            " border-radius: 6px; padding: 0 8px; font-size: 11px;"
        )

    def _build_actions_section(self) -> QGroupBox:
        group = QGroupBox("Actions")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        unlock_label = QLabel("Débloquer")
        layout.addWidget(unlock_label)

        self._unlock_spin = QSpinBox()
        self._unlock_spin.setRange(1, 50)
        self._unlock_spin.setValue(5)
        self._unlock_spin.setFixedWidth(70)
        layout.addWidget(self._unlock_spin)

        unlock_btn = QPushButton("contacts")
        unlock_btn.setFixedWidth(140)
        unlock_btn.clicked.connect(self._unlock_contacts)
        layout.addWidget(unlock_btn)
        self._unlock_btn = unlock_btn

        layout.addStretch()

        import_btn = QPushButton("Importer dans mes contacts")
        import_btn.clicked.connect(self._import_unlocked)
        layout.addWidget(import_btn)
        self._import_btn = import_btn

        return group

    # Seuils pour le badge de saturation (nombre de prises de contact dans la base)
    _SATURATION_WARN = 5       # orange dès 5 contacts
    _SATURATION_HIGH = 10      # rouge dès 10 contacts

    def _build_contacts_table(self) -> QGroupBox:
        group = QGroupBox("Contacts débloqués")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Prénom", "Nom", "Société", "Pays", "Contacté", "Statut"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        return group

    # ── Contribution en masse ─────────────────────────────────────────────────

    def _bulk_contribute(self) -> None:
        self._start_contribute_worker(limit=None)

    def _bulk_contribute_sample(self) -> None:
        self._start_contribute_worker(limit=10)

    def _start_contribute_worker(self, limit: int | None) -> None:
        if self._bulk_worker and self._bulk_worker.isRunning():
            return
        if self._bulk_sample_worker and self._bulk_sample_worker.isRunning():
            return
        cfg = get_collaborative_config()
        user_id = cfg.get("user_id")
        if not user_id:
            QMessageBox.warning(self, "Non connecté", "Connectez-vous dans les paramètres.")
            return
        self._contribute_btn.setEnabled(False)
        self._contribute_sample_btn.setEnabled(False)
        self._contribute_progress.setValue(0)
        self._contribute_progress.setVisible(True)
        label = f"{limit} contacts" if limit else "tous les contacts"
        self._contribute_status.setText(f"Contribution en cours ({label})…")
        worker = BulkContributeWorker(str(user_id), limit, self)
        worker.progress.connect(self._on_contribute_progress)
        worker.finished.connect(self._on_contribute_done)
        worker.error.connect(self._on_contribute_error)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        if limit is None:
            self._bulk_worker = worker
        else:
            self._bulk_sample_worker = worker
        worker.start()

    def _on_contribute_progress(self, done: int, total: int) -> None:
        self._contribute_progress.setRange(0, max(total, 1))
        self._contribute_progress.setValue(done)

    def _on_contribute_done(self, contributed: int, skipped: int, diagnostic: str) -> None:
        self._bulk_worker = None
        self._bulk_sample_worker = None
        self._contribute_btn.setEnabled(True)
        self._contribute_sample_btn.setEnabled(True)
        self._contribute_progress.setVisible(False)
        parts = []
        if contributed:
            parts.append(f"{contributed} contact(s) partagé(s) avec succès")
        if skipped:
            detail = f" [{diagnostic}]" if diagnostic else ""
            parts.append(f"{skipped} ignoré(s){detail}")
        if not contributed and not skipped:
            parts.append("Aucun nouveau contact à partager")
        self._contribute_status.setText(" — ".join(parts))
        self._contribute_status.setStyleSheet("color: #4ade80;" if contributed else "color: #f87171;" if skipped else "color: #94a3b8;")

    def _on_contribute_error(self, message: str) -> None:
        self._bulk_worker = None
        self._bulk_sample_worker = None
        self._contribute_btn.setEnabled(True)
        self._contribute_sample_btn.setEnabled(True)
        self._contribute_progress.setVisible(False)
        self._contribute_status.setText(f"Erreur : {message}")
        self._contribute_status.setStyleSheet("color: #dc2626;")

    # ── Rafraîchissement au focus ─────────────────────────────────────────────

    def refresh(self) -> None:
        self._sync_credits()
        self._fetch_stats()
        self._load_cached_contacts()

    # ── Stats ─────────────────────────────────────────────────────────────────

    def _fetch_stats(self) -> None:
        if self._stats_worker and self._stats_worker.isRunning():
            return
        cfg = get_collaborative_config()
        user_id = cfg.get("user_id")
        if not user_id:
            return
        worker = FetchStatsWorker(str(user_id), self)
        worker.stats_ready.connect(self._on_stats_ready)
        worker.error.connect(lambda msg: None)  # silencieux — stats non critiques
        worker.stats_ready.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        # Garantit que self._stats_worker est vidé même en cas d'erreur,
        # évitant un crash PyQt "wrapped C++ object deleted" au prochain refresh.
        worker.finished.connect(lambda: setattr(self, "_stats_worker", None))
        self._stats_worker = worker
        worker.start()

    def _on_stats_ready(
        self, total: int, unlocked: int, contributed: int, top3: list
    ) -> None:
        self._stats_worker = None
        self._stat_total[1].setText(f"{total:,}".replace(",", " "))
        self._stat_unlocked[1].setText(str(unlocked))
        self._stat_contributed[1].setText(str(contributed))

        medals = ["🥇", "🥈", "🥉"]
        for i, lbl in enumerate(self._top_labels):
            if i < len(top3):
                lbl.setText(f"{medals[i]}  {top3[i]:,} contributions".replace(",", " "))
            else:
                lbl.setText(f"{medals[i]}  —")

    # ── Crédits ───────────────────────────────────────────────────────────────

    def _sync_credits(self) -> None:
        if self._credits_worker and self._credits_worker.isRunning():
            return
        cfg = get_collaborative_config()
        user_id = cfg.get("user_id")
        if not user_id:
            return
        worker = SyncCreditsWorker(str(user_id), self)
        worker.credits_updated.connect(self._on_credits_updated)
        worker.error.connect(lambda msg: self._credits_label.setText(f"Erreur : {msg}"))
        worker.credits_updated.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        # Même garantie que pour _stats_worker — évite le crash au prochain refresh.
        worker.finished.connect(lambda: setattr(self, "_credits_worker", None))
        self._credits_worker = worker
        worker.start()

    def _on_credits_updated(self, credits: int, contributions: int) -> None:
        self._credits_worker = None
        full_access = credits == -1

        # ── Badge accès complet ────────────────────────────────────────────────
        self._full_access_badge.setVisible(full_access)

        # ── Barre et label prochain palier ────────────────────────────────────
        if full_access:
            self._tier_bar.setRange(0, 100)
            self._tier_bar.setValue(100)
            self._tier_bar.setFormat("100 / 100 contributions")
            self._next_tier_label.setText("Vous avez l'accès complet à toute la base !")
            self._next_tier_label.setStyleSheet("color: #4ade80; font-size: 12px; font-weight: 700;")
            self._credits_label.setText("Débloque autant de contacts que tu veux")
            self._credits_label.setStyleSheet("color: #4ade80; font-size: 12px; font-weight: 600;")
        else:
            # Trouver le palier courant
            tier_from, tier_to, next_threshold, reward = next(
                (t for t in TIER_RANGES if contributions < t[1]),
                TIER_RANGES[-1],
            )
            self._tier_bar.setRange(tier_from, tier_to)
            self._tier_bar.setValue(contributions)
            self._tier_bar.setFormat(f"%v / {tier_to} contributions")
            remaining = tier_to - contributions
            self._next_tier_label.setText(
                f"Prochain palier : {next_threshold} contributions → {reward}"
                f"  (encore {remaining} contribution{'s' if remaining > 1 else ''})"
            )
            self._next_tier_label.setStyleSheet("color: #e2e8f0; font-size: 12px; font-weight: 600;")

            total = compute_unlockable(contributions)
            self._credits_label.setText(f"{total} contacts débloquables au total")
            self._credits_label.setStyleSheet("color: #94a3b8; font-size: 12px;")

        # ── Roadmap des paliers (chips) ────────────────────────────────────────
        milestones_thresholds = [5, 10, 20, 50, 100]
        for chip, threshold in zip(self._tier_chips, milestones_thresholds):
            if full_access or contributions >= threshold:
                chip.setStyleSheet(self._chip_style("done"))
            elif contributions < threshold and any(
                contributions >= t[0] and contributions < t[1]
                for t in TIER_RANGES
                if t[2] == threshold
            ):
                chip.setStyleSheet(self._chip_style("current"))
            else:
                # Palier cible actuel (premier non atteint)
                tier_from, tier_to, next_thresh, _ = next(
                    (t for t in TIER_RANGES if contributions < t[1]),
                    TIER_RANGES[-1],
                )
                if threshold == next_thresh:
                    chip.setStyleSheet(self._chip_style("current"))
                else:
                    chip.setStyleSheet(self._chip_style("future"))

        save_collaborative_config({"credits": contributions})
        self.credits_updated.emit(credits if credits >= 0 else 9999)

    # ── Déblocage ─────────────────────────────────────────────────────────────

    def _unlock_contacts(self) -> None:
        if self._unlock_worker and self._unlock_worker.isRunning():
            return
        cfg = get_collaborative_config()
        user_id = cfg.get("user_id")
        if not user_id:
            QMessageBox.warning(self, "Non connecté", "Connectez-vous dans les paramètres.")
            return
        count = self._unlock_spin.value()
        self._unlock_btn.setEnabled(False)
        worker = UnlockContactsWorker(str(user_id), count, self)
        worker.contacts_unlocked.connect(self._on_contacts_unlocked)
        worker.error.connect(self._on_unlock_error)
        worker.contacts_unlocked.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._unlock_worker = worker
        worker.start()

    def _on_contacts_unlocked(self, contacts: list) -> None:
        self._unlock_worker = None
        self._unlock_btn.setEnabled(True)
        self._load_cached_contacts()
        self._sync_credits()
        QMessageBox.information(
            self, "Déblocage", f"{len(contacts)} contact(s) débloqué(s) avec succès."
        )

    def _on_unlock_error(self, message: str) -> None:
        self._unlock_worker = None
        self._unlock_btn.setEnabled(True)
        QMessageBox.critical(self, "Erreur déblocage", message)

    # ── Import local ──────────────────────────────────────────────────────────

    def _import_unlocked(self) -> None:
        if self._import_worker and self._import_worker.isRunning():
            return
        cfg = get_collaborative_config()
        user_id = cfg.get("user_id")
        if not user_id:
            QMessageBox.warning(self, "Non connecté", "Connectez-vous dans les paramètres.")
            return
        self._import_btn.setEnabled(False)
        worker = ImportUnlockedWorker(str(user_id), self)
        worker.import_done.connect(self._on_import_done)
        worker.error.connect(self._on_import_error)
        worker.import_done.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._import_worker = worker
        worker.start()

    def _on_import_done(self, created: int) -> None:
        self._import_worker = None
        self._import_btn.setEnabled(True)
        self._load_cached_contacts()
        QMessageBox.information(
            self, "Import", f"{created} nouveau(x) contact(s) importé(s) dans vos contacts."
        )

    def _on_import_error(self, message: str) -> None:
        self._import_worker = None
        self._import_btn.setEnabled(True)
        QMessageBox.critical(self, "Erreur import", message)

    # ── Chargement du cache local ─────────────────────────────────────────────

    def _load_cached_contacts(self) -> None:
        """Affiche les contacts débloqués depuis collab_unlocked_cache."""
        from app.db.session import SessionLocal
        from app.models.collaborative_state import CollabUnlockedCache
        from sqlalchemy import select

        db = SessionLocal()
        try:
            rows = db.scalars(select(CollabUnlockedCache).order_by(
                CollabUnlockedCache.unlocked_at.desc()
            )).all()
        finally:
            db.close()

        self._table.setRowCount(len(rows))
        group_title = f"Contacts débloqués ({len(rows)})"
        parent_group = self._table.parent()
        if isinstance(parent_group, QGroupBox):
            parent_group.setTitle(group_title)

        for row_idx, row in enumerate(rows):
            self._table.setItem(row_idx, 0, QTableWidgetItem(row.first_name or ""))
            self._table.setItem(row_idx, 1, QTableWidgetItem(row.last_name or ""))
            self._table.setItem(row_idx, 2, QTableWidgetItem(row.company_name or ""))
            self._table.setItem(row_idx, 3, QTableWidgetItem(row.country or ""))

            # ── Badge saturation ──────────────────────────────────────────────
            count = row.contact_count or 0
            if count == 0:
                contact_text = "Jamais contacté"
                contact_color = Qt.GlobalColor.darkGreen
            elif count < self._SATURATION_WARN:
                contact_text = str(count)
                contact_color = Qt.GlobalColor.gray
            elif count < self._SATURATION_HIGH:
                contact_text = f"⚠ {count}"
                contact_color = Qt.GlobalColor.yellow
            else:
                contact_text = f"● Saturé ({count})"
                contact_color = Qt.GlobalColor.red
            contact_item = QTableWidgetItem(contact_text)
            contact_item.setForeground(contact_color)
            if count >= self._SATURATION_WARN:
                contact_item.setToolTip(
                    f"Ce prospect a été contacté {count} fois au total dans la base."
                )
            self._table.setItem(row_idx, 4, contact_item)

            status = "✓ Importé" if row.imported_to_local else "En attente"
            item = QTableWidgetItem(status)
            item.setForeground(
                Qt.GlobalColor.darkGreen if row.imported_to_local else Qt.GlobalColor.gray
            )
            self._table.setItem(row_idx, 5, item)
