# OIP v0.6.0 — Lot 5 : alertes locales et rapports JSON/CSV

## Périmètre réel

- Moteur d'alertes **local en base PostgreSQL**, sans notifications sortantes, webhook ni email.
- Génération au moment de la collecte réussie et autorisée de nouveaux signaux :
  `WATCHLIST_MATCH`, `CTI_SIGNAL`, `CONTENT_CHANGED`, `RELEVANCE_THRESHOLD`
  (seuil initial 70) et `SENSITIVE_REVIEW` (revue humaine requise).
- Pour une page sensible mise en quarantaine : **uniquement** `SENSITIVE_REVIEW`,
  sans extrait, sans autre alerte CTI, sans réactivation de la collecte.
- Déduplication SHA-256 fondée sur `source_id + empreinte texte + type d'événement + clé stable`.
  Une seconde observation du même texte n'émet pas le même signal. Une modification
  de contenu peut déclencher un nouveau signal. Le moteur est idempotent lors d'un
  nouvel appel sur la même observation, y compris en présence de tentatives simultanées.
- L'alerte ne signifie **ni compromission vérifiée ni attribution certaine**.
- API protégée par `X-API-Key` ; transitions `OPEN -> ACKNOWLEDGED -> RESOLVED`
  (ou `OPEN -> RESOLVED`), immuables après résolution, avec audit. Le champ
  `reason` a pour valeur par défaut `Manual check` et n'est pas exporté.
- Rapports **figés** : instantanés enregistrés dans PostgreSQL. Export JSON/CSV
  dérivé uniquement du snapshot ; modifier la base après création ne change pas le fichier.
- Les données exportées sont des UUID, codes, scores, confiances, statuts et dates.
  Les URL Onion, titres, descriptions, phrases de watchlist, extraits, HTML,
  secrets et justifications ne sont **jamais inclus**.
- `max_rows_per_type` borné entre 1 et 200 ; par défaut 100. Les totaux sont
  distincts du nombre de lignes exportées ; `truncated_types` indique les limites.
- Périodes demandées en dates ISO 8601 avec fuseaux horaires, max 366 jours,
  intervalle `[period_start, period_end[`.

## Installation sur la branche du lot 5

```bash
cd ~/onion-intelligence-platform
git switch -c feature/lot5-alerts-reports
unzip -o ~/Downloads/OIP_lot5_alertes_rapports_v0.6.0.zip -d .
sudo docker compose config --quiet
sudo docker compose --profile test run --build --rm tests
sudo docker compose up --build -d
sudo docker compose exec api alembic current
# attendu : 0006_alerts_reports (head)
curl -fsS http://127.0.0.1:8000/api/ready
```

**Migration :** `0006_alerts_reports`, crée uniquement `alerts` et `reports`.
Elle n'altère ni sources, ni observations, ni tables CTI. Aucune alerte rétroactive
n'est créée sur les observations historiques : les alertes arrivent lors de futures
collectes autorisées. Ne pas effacer les volumes PostgreSQL.

## Routes FastAPI

| Verbe | Route | Résultat |
|---|---|---|
| GET | `/api/v1/alerts` | Liste avec `source_id`, `status`, `event_type`, `priority`, `limit`, `offset` |
| GET | `/api/v1/alerts/{id}` | Détail sans raison ni contenu brut |
| PATCH | `/api/v1/alerts/{id}` | Révision manuelle de l'état, journalisée |
| POST | `/api/v1/reports` | Création et persistance d'un instantané borné |
| GET | `/api/v1/reports` | Liste de métadonnées de rapports |
| GET | `/api/v1/reports/{id}` | Métadonnées d'un rapport |
| GET | `/api/v1/reports/{id}/export?format=json` | JSON figé |
| GET | `/api/v1/reports/{id}/export?format=csv` | CSV figé |

## Exemples, sans secret dans les logs ni sur la ligne de commande

```bash
read -rsp 'OIP API key: ' OIP_KEY; echo
curl -fsS -H "X-API-Key: $OIP_KEY" \
  http://127.0.0.1:8000/api/v1/alerts?status=OPEN | python3 -m json.tool
```

Révision d'une alerte :

```bash
ALERT_ID='<UUID from GET /api/v1/alerts>'
curl -fsS -X PATCH "http://127.0.0.1:8000/api/v1/alerts/$ALERT_ID" \
  -H "X-API-Key: $OIP_KEY" -H 'Content-Type: application/json' \
  -d '{"status":"ACKNOWLEDGED","reason":"Manual check"}'
```

Rapport des dernières 24 heures (dates en UTC calculées sur le poste) :

```bash
REPORT_JSON=$(python3 - <<'PY'
from datetime import datetime, timedelta, timezone
import json
now=datetime.now(timezone.utc)
print(json.dumps({"period_start":(now-timedelta(days=1)).isoformat(),
                  "period_end":(now+timedelta(minutes=1)).isoformat(),
                  "max_rows_per_type":100}))
PY
)
curl -fsS -X POST http://127.0.0.1:8000/api/v1/reports \
  -H "X-API-Key: $OIP_KEY" -H 'Content-Type: application/json' \
  -d "$REPORT_JSON" | python3 -m json.tool
# Copier l'id retourné et remplacer REPORT_ID ci-dessous.
REPORT_ID='<UUID from POST /api/v1/reports>'
curl -fsS -H "X-API-Key: $OIP_KEY" \
  "http://127.0.0.1:8000/api/v1/reports/$REPORT_ID/export?format=json" \
  -o oip-report.json
curl -fsS -H "X-API-Key: $OIP_KEY" \
  "http://127.0.0.1:8000/api/v1/reports/$REPORT_ID/export?format=csv" \
  -o oip-report.csv
unset OIP_KEY
```

Les fichiers de rapport locaux (`oip-report.json`, `oip-report.csv`) doivent être
traités comme données internes. Les placer hors du dépôt Git ; ne pas les publier.

## Tests et limites

- Tests locaux : pytest, FastAPI/SQLite, collecte HTML simulée, migration depuis
  une base v0.5.0 avec données existantes, vérifications d'export et de déduplication.
- **Pas** de Docker Engine, PostgreSQL 17 ni Tor réel dans le contexte de
  génération de ce lot : ceux-ci doivent être validés sur le poste opérateur.
- Pas de notification asynchrone, pas de scheduler, pas de dashboard, pas de
  confirmation indépendante des revendications ni de relecture automatisée
  des anciennes observations. Pas de RBAC ; clé API partagée uniquement.
- Les rapports sont persistants : politique de rétention et suppression
  auditable à développer avant production. Un export CSV contient des
  métadonnées seulement, non une preuve d'incident.
- La génération par traitement d'une observation produit au maximum 128 alertes ;
  les alertes jugées plus importantes sont retenues en priorité.
- Une base contenant de nombreuses observations peut nécessiter une politique
  de quotas et un indexage temporel supplémentaire avant montée en charge.

## Versionnement

```bash
git add -A
git diff --cached --check
git commit -m "feat: add deduplicated alerts and immutable reports - lot 5"
git tag -a v0.6.0-lot5 -m "OIP lot 5 validated"
```
