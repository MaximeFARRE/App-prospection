from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base déclarative partagée par tous les modèles SQLAlchemy.

    Tous les modèles doivent hériter de cette classe.
    Alembic l'importe via env.py pour détecter les changements de schéma.

    Usage :
        from app.db.base import Base

        class Contact(Base):
            __tablename__ = "contacts"
            ...
    """

    pass
