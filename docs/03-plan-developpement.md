from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.sources import router as sources_router
from app.api.collection import router as collection_router
from app.api.intelligence import router as intelligence_router
from app.api.cti import router as cti_router

app = FastAPI(
    title="Onion Intelligence Platform API",
    description="Collecte Tor contrôlée et manuelle, classification hors ligne et signaux CTI non vérifiés.",
    version="0.5.0",
)
app.include_router(health_router)
app.include_router(sources_router)
app.include_router(collection_router)
app.include_router(intelligence_router)
app.include_router(cti_router)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


## Extension lot 4 (migration `0005_cti_classification`)

- `classification_results` : UUID de l'observation et de la source ; catégorie suggérée ; confiance heuristique ; liste JSON de **codes** de règles ; version du moteur ; statut de revue (`AUTO_SUGGESTED`, `REVIEW_REQUIRED`, `ACCEPTED`, `REJECTED`) ; métadonnées de revue. Contrainte unique `(observation_id, category)`.
- `threat_indicators` : UUID de l'observation et de la source ; type de signal ; `public_reference` (CVE uniquement) ; `verification_status` (`OBSERVED_REFERENCE` ou `OBSERVED_CLAIM`) ; confiance heuristique ; codes d'évidence et version. Contrainte unique `(observation_id, indicator_type, public_reference)`.
- `correlations` : **vue calculée à la demande**, aucune table supplémentaire. Jointure non intrusive sur `observation_id` entre `threat_indicators` et `keyword_matches` puis `watchlist_rules`; aucun extrait ni secret exposé.
- Les observations lot 3 existantes sont conservées et ne sont pas rétro-classifiées. Les nouveaux champs ne sont pas ajoutés aux anciennes tables.
- Les classifications proposées et les revendications ne sont **pas** une preuve, une confirmation ou une attribution.


## Avancement lot 4 — v0.5.0

Le socle de classification déterministe, les signaux CTI (CVE publics et revendications), le filtrage API, la revue humaine et la cooccurrence avec les watchlists sont implémentés ; 135 tests locaux réussis. Aucun enrichissement externe automatique et aucune collecte hors périmètre n'ont été ajoutés. La validation sur PostgreSQL réel, la calibration des règles, les alertes et les rapports restent à effectuer. Voir `docs/10-lot4-cti-classification.md`.
