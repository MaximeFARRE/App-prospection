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

from views.dashboard_view import DashboardView
from views.contacts_view import ContactsView
from views.imports_view import ImportsView
from views.campaigns_view import CampaignsView
from views.replies_view import RepliesView
from views.settings_view import SettingsView


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("App Prospection")
        self.setMinimumSize(1200, 720)
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
            ("📊  Dashboard",  0),
            ("👥  Contacts",   1),
            ("📥  Imports",    2),
            ("📨  Campagnes",  3),
            ("💬  Réponses",   4),
            ("⚙️  Paramètres", 5),
        ]

        self._nav_buttons: list[QPushButton] = []
        for label, index in nav_items:
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
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        layout.addStretch()
        return sidebar

    def _make_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        for view in [
            DashboardView(),
            ContactsView(),
            ImportsView(),
            CampaignsView(),
            RepliesView(),
            SettingsView(),
        ]:
            self._stack.addWidget(view)
        return self._stack

    # ──────────────────────────────────────────────────────────────────────────
    # Navigation
    # ──────────────────────────────────────────────────────────────────────────

    def _navigate(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)

        current_view = self._stack.widget(index)
        refresh = getattr(current_view, "refresh", None)
        if callable(refresh):
            refresh()
