from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# check_same_thread=False est requis pour SQLite en mode multi-thread (FastAPI).
# L'option est ignorée silencieusement par d'autres moteurs (PostgreSQL, etc.).
connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,  # passer à True en dev pour voir les requêtes SQL dans les logs
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Dépendance FastAPI : fournit une session SQLAlchemy par requête HTTP.

    La session est fermée automatiquement après chaque requête, même en cas
    d'exception.

    Usage dans une route :
        from app.db.session import get_db

        @router.get("/contacts")
        def list_contacts(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
