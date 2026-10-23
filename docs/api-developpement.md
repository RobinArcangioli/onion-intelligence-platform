# API et développement

*OIP v1.0.0-rc2 · Document de référence pour la maintenance du code gelé*

## Composants et commandes

| Emplacement | Responsabilité |
|---|---|
| `backend/app/api/` | Routes FastAPI authentifiées et lecture de données |
| `backend/app/collector/` | Transport Tor, traitement d'une source et worker de jobs manuels |
| `backend/app/models/` | Tables SQLAlchemy réellement implémentées |
| `backend/alembic/versions/` | Migrations historiques indispensables (0001 à 0008) |
| `backend/tests/` | Régressions, rôles, migrations et confinement |
| `frontend/src/` | Pages React, navigation et API cliente same-origin |
| `frontend/e2e/` | Tests navigateur Playwright sans collecte réelle |
| `infrastructure/` | Nginx et Tor ; configuration réseau dans `compose.yaml` |
| `scripts/` | Validation, restauration, audit des dépendances et contrôle Git |

## API HTTP

Le navigateur s'adresse **uniquement** à l'origine locale. Toutes les routes métier protégées utilisent l'en-tête `X-API-Key: <jeton-personnel>`. La documentation interactive FastAPI est accessible localement par `/docs` et `/openapi.json` lorsque la passerelle tourne. Ne publiez pas leur URL sur une interface publique.

| Route / groupe | Usage |
|---|---|
| `GET /api/health`, `GET /api/ready` | Santé du processus et disponibilité PostgreSQL |
| `GET /api/v1/auth/me` | Identité, rôle, ancienneté du type de jeton |
| `/api/v1/sources` | Sources, filtres, création, modification, audit et approbations |
| `POST /api/v1/sources/{id}/collection/run` | **Créer un job manuel** (`ANALYST`/`ADMIN`, motif requis ; HTTP 202) |
| `/api/v1/collection/jobs`, `/observations`, `/discoveries`, `/latest` | Statuts, résultats, candidates, dernier job par source |
| `/api/v1/watchlists` | Listes et règles de veille |
| `/api/v1/cti` | Classifications, indicateurs et corrélations |
| `/api/v1/alerts`, `/api/v1/reports` | Alertes et snapshots/export JSON/CSV |

Les routes détaillées, schémas de requête et codes HTTP sont définis dans **OpenAPI**, qui est la source de vérité, et non dans une liste copiée susceptible de devenir obsolète.

Exemple de création d'un job ponctuel (jeton fourni sans l'écrire dans l'historique du shell) :

```bash
read -rsp 'Personal token: ' OIP_TOKEN; echo
read -rp 'Approved source UUID: ' SOURCE_ID
OIP_TOKEN="$OIP_TOKEN" SOURCE_ID="$SOURCE_ID" python3 - <<'PY'
import json, os, urllib.request
url = f"http://127.0.0.1:8000/api/v1/sources/{os.environ['SOURCE_ID']}/collection/run"
request = urllib.request.Request(url, data=json.dumps({'reason':'Manual check'}).encode(),
    headers={'X-API-Key':os.environ['OIP_TOKEN'],'Content-Type':'application/json'}, method='POST')
with urllib.request.urlopen(request, timeout=10) as response:
    print('HTTP', response.status)
PY
unset OIP_TOKEN SOURCE_ID
```

**Cette commande déclenche réellement une tâche** : ne l'utilisez que pour une source autorisée. Préférez le bouton de l'interface pour l'exploitation courante.

## Tests et builds

```bash
sudo docker compose --profile test run --build --rm tests   # backend isolé, aucun réseau
sudo bash scripts/validate-v1.sh --core                    # + vérifications runtime et restauration temporaire
sudo bash scripts/validate-v1.sh --release                 # + audits en ligne, navigateur Chromium
(cd frontend && npm ci --ignore-scripts --no-fund && npm run test:unit && npm run typecheck && npm run build)
```

`frontend/package-lock.json` est exigé pour une reproduction fiable ; il doit être committé après génération locale. La suite `--release` nécessite un jeton nominatif, `OIP_LEGACY_API_KEY_ENABLED=false` et Chromium disponible pour Playwright. Les tests unitaires et navigateur ne doivent pas effectuer de collecte Onion.

Le **gel d'implémentation** interdit les changements de fonctionnalité en phase de polissage GitHub. Toute correction future devra être bornée, relue, testée et versionnée explicitement. Ne supprimez ni les anciens tests (`test_*_lot*`) ni les migrations historiques : ils protègent l'upgrade depuis les versions précédentes.

## Qualité, contribution et sécurité

- Contrôlez l'absence de `.env`, dumps, jetons, archives, caches, exports et médias dans l'index **et l'historique Git**.
- Pas de clé ou de source Onion réelle dans les fixtures publiques. Les tests emploient des exemples synthétiques.
- Évitez les logs de requêtes contenant URL complètes, corps HTML, en-têtes d'authentification ou réponses dangereuses.
- Documentez la provenance d'un nouveau signal ; aucun score heuristique ne doit être présenté comme une preuve.
- Toute modification à `compose.yaml` doit préserver le rôle unique de `gateway` pour les ports hôtes et le confinement `collector`/`queue_worker`.

Le contrôle local `python3 scripts/pre-push-audit.py` applique une **liste d'exclusion prudente** et inspecte les contenus indexés et l'historique Git. Il n'envoie aucune donnée sur Internet et n'affiche jamais la valeur des secrets suspectés.
