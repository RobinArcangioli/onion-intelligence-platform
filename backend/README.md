**Lot 4 (v0.5.0) :** voir `../docs/10-lot4-cti-classification.md` pour classification hors ligne, indicateurs CTI et revue humaine.

**Lot 3 (v0.4.0) :** voir `../docs/09-lot3-analyse-decouverte.md` pour watchlists, scores et découvertes.

**Lot 2 (0.3.0) :** voir `../docs/08-lot2-collecte-tor.md` pour la collecte ponctuelle Tor et les nouvelles migrations.

# OIP API

Module Python du MVP de la plateforme. Pour les instructions de démarrage, voir `../README.md`.


## Lot 5 — alertes et rapports (v0.6.0)

Deux nouvelles tables `alerts` et `reports`, migrations Alembic `0006_alerts_reports`.
Routes protégées `GET/PATCH /api/v1/alerts`, `GET/POST /api/v1/reports`,
`GET /api/v1/reports/{id}/export?format=json|csv`.
Les rapports sont des snapshots metadata-only; aucune navigation Onion supplémentaire.
Voir `../docs/11-lot5-alertes-rapports.md`.
