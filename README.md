# ONION INTELLIGENCE PLATFORM (OIP)

**Version :** 0.1.0 — Lot 0, fondations locales.  
**Statut :** code initial et tests locaux opérationnels; déploiement Docker/PostgreSQL réel **non exécuté dans l'environnement de livraison** (Docker indisponible).  
**Langue de la documentation :** français.

Plateforme de veille documentaire sur sources Onion publiques et explicitement autorisées. Cette livraison implémente le socle de gestion de sources, sans aucun accès Tor. Elle **ne** découvre, ne visite, ne télécharge et ne classe aucun site à ce stade.

## Fonctionnalités présentes

- FastAPI avec `GET /api/health` et `GET /api/ready`.
- SQLAlchemy + Alembic : tables `onion_sources` et `audit_logs`.
- API `GET/POST /api/v1/sources`, authentifiée par `X-API-Key`.
- Ajout manuel exigeant `authorization_confirmed=true` et une note descriptive d'autorisation.
- Validation syntaxique et checksum des racines `.onion` v3; aucun accès réseau.
- Journal d'audit de création, réponse 409 sur doublon, pagination.
- PostgreSQL 17 et API définis dans Docker Compose (aucun port DB publié, API sur loopback).
- Tests hors ligne utilisant SQLite en mémoire et migration SQLite temporaire.

## Arborescence exacte — fichiers présents

```text
onion-intelligence-platform/
├── .dockerignore
├── .env.example
├── .gitignore
├── compose.yaml
├── README.md
├── backend/
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── README.md
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 0001_bootstrap.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── health.py
│   │   │   └── sources.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   └── config.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── audit.py
│   │   │   └── source.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   └── source.py
│   │   └── security/
│   │       ├── __init__.py
│   │       ├── api_key.py
│   │       └── onion.py
│   └── tests/
│       ├── conftest.py
│       ├── test_api.py
│       ├── test_migration.py
│       └── test_validation.py
└── docs/
    ├── bootstrap-postgresql-preview.sql
    ├── 00-cadrage.md
    ├── 01-architecture.md
    ├── 02-modele-donnees.md
    ├── 03-plan-developpement.md
    ├── 04-validation.md
    ├── 05-etat-du-projet.md
    └── 06-securite.md
```

**Pas encore créés (et volontairement absents) :** `frontend/`, `infrastructure/tor/`, `app/crawler/`, `app/discovery/`, `app/analyzers/`, `app/scoring/`, `app/alerts/`, `app/reports/`. Voir `docs/03-plan-developpement.md`.

## Installer et lancer avec Docker Compose

Pré-requis : Docker Engine, Compose V2, accès au registre Docker et aux paquets Python lors de la construction. Les commandes s'exécutent à la racine du dépôt.

```bash
cp .env.example .env
python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('.env')
s = p.read_text()
s = s.replace('replace_with_long_random_password', secrets.token_hex(24))
s = s.replace('replace_with_a_long_random_secret_at_least_32_chars', secrets.token_hex(32))
p.write_text(s)
PY

docker compose up --build -d
docker compose ps
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/ready
```

Au démarrage de `api`, `alembic upgrade head` applique les migrations à PostgreSQL **avant** le lancement d'Uvicorn. `api` attend que le `healthcheck` de `db` devienne sain. Si la migration échoue, le processus API ne démarre pas.

Réponses attendues :

```json
{"status":"ok","service":"oip-api"}
{"status":"ready","database":"reachable"}
```

Inspecter les tables :

```bash
docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\\dt"'
docker compose logs --tail=100 api
docker compose exec api alembic current
```

OpenAPI : `http://127.0.0.1:8000/docs` (accès local uniquement; documentation interactive non destinée à Internet).

### Ajouter une source synthétique pour vérifier la persistance

La valeur ci-dessous est fabriquée uniquement pour les tests de structure : **ce n'est pas un service que le projet tente de joindre**.

```bash
export OIP_API_KEY="$(grep '^OIP_API_KEY=' .env | cut -d= -f2-)"
curl -sS -X POST http://127.0.0.1:8000/api/v1/sources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $OIP_API_KEY" \
  -d '{"url":"http://aaaqeayeaudaocajbifqydiob4ibceqtcqkrmfyydenbwha5dyp3kead.onion/","name":"Source fictive","description":"Test sans accès Tor","authorization_confirmed":true,"authorization_note":"Adresse fictive réservée au test local"}'

curl -sS -H "X-API-Key: $OIP_API_KEY" \
  'http://127.0.0.1:8000/api/v1/sources?limit=10&offset=0'
```

La source est en `NOT_CHECKED` et `collection_enabled=false`. Aucune connexion n'a lieu. La confirmation d'autorisation dans ce prototype est une déclaration de l'opérateur, **pas** une preuve juridique.

## Tests

Depuis la racine :

```bash
docker compose --profile test run --build --rm tests
```

Ou localement avec Python 3.12/3.13, sans Docker :

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q -p no:cacheprovider
```

**Note :** le test de migration inclus valide Alembic sur un fichier SQLite temporaire; le test d'intégration PostgreSQL/Docker doit être exécuté séparément. Lire `docs/04-validation.md` pour les résultats réellement obtenus.

## Arrêt et conservation des données

```bash
docker compose down
```

La commande ci-dessus conserve le volume PostgreSQL. **Attention :** `docker compose down -v` détruit les données de la base locale; effectuer une sauvegarde avant toute suppression.

## Sécurité / limites actuelles

- **Local uniquement** : clé API partagée (pas encore de RBAC), docs OpenAPI non protégées, aucun reverse proxy TLS.
- **Aucun réseau Tor** : l'architecture Tor et les règles de sortie réseau doivent être développées et auditées avant toute collecte.
- Les seules données autorisées en entrée sont l'URL v3, un nom, une description et une note d'autorisation.
- Pas d'écriture de contenu collecté, pas de JS, pas d'archives, pas de médias ni de mots de passe.
- La protection Docker par réseau privé et utilisateur non privilégié ne vaut pas garantie de confinement contre toutes les menaces.
- `pyproject.toml` borne les versions majeures mais n'est pas un lockfile reproductible octet par octet; verrouiller les dépendances et les digests d'images avant déploiement de production.

## Index documentaire

1. [`docs/00-cadrage.md`](docs/00-cadrage.md) — analyse des exigences et risques.
2. [`docs/01-architecture.md`](docs/01-architecture.md) — diagrammes Mermaid, composants et flux.
3. [`docs/02-modele-donnees.md`](docs/02-modele-donnees.md) — modèle PostgreSQL cible et tables initiales.
4. [`docs/03-plan-developpement.md`](docs/03-plan-developpement.md) — lots, fichiers et critères d'acceptation.
5. [`docs/04-validation.md`](docs/04-validation.md) — tests effectivement exécutés et tests restants.
6. [`docs/05-etat-du-projet.md`](docs/05-etat-du-projet.md) — état versionnable et décisions techniques.
7. [`docs/06-securite.md`](docs/06-securite.md) — menaces, barrières et garde-fous.

## Initialiser Git

```bash
git init
git add .
git commit -m "feat: bootstrap OIP API, database schema and offline tests"
```

Le fichier `.env` n'est pas inclus dans l'archive et est exclu de Git par `.gitignore`.
