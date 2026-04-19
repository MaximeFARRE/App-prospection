import os
import sys

# Rend les modules apps/api/app/* importables directement depuis le desktop
_DESKTOP_DIR = os.path.dirname(os.path.abspath(__file__))
_API_DIR = os.path.join(_DESKTOP_DIR, "..", "api")
sys.path.insert(0, _DESKTOP_DIR)  # views/, widgets/
sys.path.insert(0, _API_DIR)      # app.models, app.services, etc.

from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.db.base import Base              # noqa: E402
from app.db.schema_compat import ensure_schema_compatibility  # noqa: E402
from app.db.session import engine         # noqa: E402
from services.settings_service import apply_runtime_overrides  # noqa: E402
from views.main_window import MainWindow  # noqa: E402


def main() -> None:
    apply_runtime_overrides()

    # Crée les tables manquantes au premier lancement
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility(engine)

    app = QApplication(sys.argv)
    app.setApplicationName("App Prospection")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
