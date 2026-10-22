from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.sources import router as sources_router
from app.api.collection import router as collection_router

app = FastAPI(
    title="Onion Intelligence Platform API",
    description="Initialisation sécurisée : registre manuel de sources, collecte Tor manuelle, contrôlée et désactivée par défaut.",
    version="0.3.0",
)
app.include_router(health_router)
app.include_router(sources_router)
app.include_router(collection_router)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response
