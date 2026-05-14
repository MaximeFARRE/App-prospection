from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services.settings_service import get_collaborative_config
from views.campaigns_view import CampaignsView
from views.collaborative_view import CollaborativeView
from views.contacts_view import ContactsView
from views.dashboard_view import DashboardView
from views.imports_view import ImportsView
from views.replies_view import RepliesView
from views.settings_view import SettingsView
from views.templates_view import TemplatesView


class MainWindow(QMainWindow):
    # Index fixe de l'onglet collaboratif dans le stack (après les 7 vues fixes)
    _COLLAB_STACK_INDEX = 7

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("App Prospection")
        self.setMinimumSize(1200, 720)
        self._collab_nav_btn: QPushButton | None = None
        self._collab_view: CollaborativeView | None = None
        self._build_ui()
        self._navigate(0)  # Dashboard par défaut

    # ──────────────────────────────────────────────────────────────────────────
    # Construction de l'interface
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._make_sidebar())
        layout.addWidget(self._make_stack(), stretch=1)

    def _make_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(190)
        sidebar.setStyleSheet("background-color: #1e293b;")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Titre
        title = QLabel("Prospection")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFixedHeight(56)
        title.setStyleSheet("color: #f8fafc; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Boutons de navigation
        nav_items = [
            ("📊  Dashboard",   0),
            ("👥  Contacts",    1),
            ("📥  Imports",     2),
            ("📨  Campagnes",   3),
            ("💬  Réponses",    4),
            ("📝  Templates",   5),
            ("⚙️  Paramètres",  6),
        ]

        self._nav_buttons: list[QPushButton] = []
        for label, index in nav_items:
            btn = self._make_nav_btn(label, index)
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        # Bouton collaboratif — visible seulement si le mode est activé
        collab_btn = self._make_nav_btn("🤝  Collaboratif", self._COLLAB_STACK_INDEX)
        collab_btn.setVisible(
            bool(get_collaborative_config().get("enabled", False))
        )
        layout.addWidget(collab_btn)
        self._collab_nav_btn = collab_btn

        layout.addStretch()
        return sidebar

    def _make_nav_btn(self, label: str, index: int) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setFixedHeight(44)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                text-align: left;
                padding-left: 20px;
                font-size: 13px;
            }
            QPushButton:hover  { background: #334155; color: #f1f5f9; }
            QPushButton:checked { background: #0f172a; color: #ffffff;
                                  border-left: 3px solid #3b82f6; }
        """)
        btn.clicked.connect(lambda _, i=index: self._navigate(i))
        return btn

    def _make_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._settings_view = SettingsView()
        self._settings_view.collaborative_toggled.connect(self._on_collaborative_toggled)
        for view in [
            DashboardView(),
            ContactsView(),
            ImportsView(),
            CampaignsView(),
            RepliesView(),
            TemplatesView(),
            self._settings_view,
        ]:
            self._stack.addWidget(view)

        # Slot collaboratif : toujours présent dans le stack, masqué si désactivé
        self._collab_view = CollaborativeView()
        self._stack.addWidget(self._collab_view)   # index == _COLLAB_STACK_INDEX

        return self._stack

    def _on_collaborative_toggled(self, enabled: bool) -> None:
        if self._collab_nav_btn:
            self._collab_nav_btn.setVisible(enabled)
        # Si on désactive alors qu'on est sur la vue collaborative, retour au dashboard
        if not enabled and self._stack.currentIndex() == self._COLLAB_STACK_INDEX:
            self._navigate(0)

    # ──────────────────────────────────────────────────────────────────────────
    # Navigation
    # ──────────────────────────────────────────────────────────────────────────

    def _navigate(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        if self._collab_nav_btn:
            self._collab_nav_btn.setChecked(index == self._COLLAB_STACK_INDEX)

        current_view = self._stack.widget(index)
        refresh = getattr(current_view, "refresh", None)
        if callable(refresh):
            refresh()
