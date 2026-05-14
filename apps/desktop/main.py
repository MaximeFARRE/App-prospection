import os
import sys
import traceback
import logging
from pathlib import Path

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

_LOG_FILE = Path(_DESKTOP_DIR) / "app.log"

_fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s")

_file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(_fmt)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setLevel(logging.DEBUG)
_console_handler.setFormatter(_fmt)

logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger().addHandler(_file_handler)
logging.getLogger().addHandler(_console_handler)
# Réduire le bruit des bibliothèques tierces
for _noisy in ("httpx", "httpcore", "urllib3", "postgrest"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    """Log unhandled exceptions to crash.log and stderr, then let Python handle them."""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.error("Unhandled exception:\n%s", msg)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _excepthook


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
