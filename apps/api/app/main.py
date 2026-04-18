from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.api import (
    routes_contacts,
    routes_imports,
    routes_campaigns,
    routes_messages,
    routes_replies,
    routes_dashboard,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Crée les tables au démarrage si elles n'existent pas.

    En production, les migrations Alembic prennent le relais.
    Ce create_all sert uniquement de filet de sécurité en dev.
    """
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="App Prospection",
    description="CRM de prospection pour stages en finance.",
    version="0.1.0",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Autorise le frontend Vite (port 5173) à appeler l'API pendant le développement.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ───────────────────────────────────────────────────────────────────
app.include_router(routes_dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(routes_contacts.router, prefix="/contacts", tags=["Contacts"])
app.include_router(routes_imports.router, prefix="/imports", tags=["Imports"])
app.include_router(routes_campaigns.router, prefix="/campaigns", tags=["Campaigns"])
app.include_router(routes_messages.router, prefix="/messages", tags=["Messages"])
app.include_router(routes_replies.router, prefix="/replies", tags=["Replies"])


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Endpoint de vérification rapide que l'API tourne."""
    return {"status": "ok"}
