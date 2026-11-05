from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.sources import router as sources_router
from app.api.collection import router as collection_router
from app.api.intelligence import router as intelligence_router
from app.api.cti import router as cti_router
from app.api.reporting import router as reporting_router
from app.api.auth import router as auth_router
from app.api.schedules import router as schedules_router
from app.api.observations import router as observations_router
from app.api.cases import router as cases_router
from app.api.case_operations import router as case_operations_router

from app.api.public import router as public_router
from app.api.report_publications import router as report_publications_router

app = FastAPI(
    title="Onion Intelligence Platform API",
    description="Collecte Tor contrôlée et manuelle, classification hors ligne et signaux CTI non vérifiés.",
    version="1.0.0-rc2",
)
app.include_router(health_router)
app.include_router(public_router)
app.include_router(report_publications_router)
app.include_router(sources_router)
app.include_router(collection_router)
app.include_router(intelligence_router)
app.include_router(cti_router)
app.include_router(reporting_router)
app.include_router(auth_router)
app.include_router(schedules_router)
app.include_router(observations_router)
app.include_router(cases_router)
app.include_router(case_operations_router)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    return response
