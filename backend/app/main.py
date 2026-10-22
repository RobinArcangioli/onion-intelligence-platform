from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.sources import router as sources_router
from app.api.collection import router as collection_router
from app.api.intelligence import router as intelligence_router
from app.api.cti import router as cti_router
from app.api.reporting import router as reporting_router

app = FastAPI(
    title="Onion Intelligence Platform API",
    description="Collecte Tor contrôlée et manuelle, classification hors ligne et signaux CTI non vérifiés.",
    version="0.6.0",
)
app.include_router(health_router)
app.include_router(sources_router)
app.include_router(collection_router)
app.include_router(intelligence_router)
app.include_router(cti_router)
app.include_router(reporting_router)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response
