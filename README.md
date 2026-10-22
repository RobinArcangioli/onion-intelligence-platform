# ONION INTELLIGENCE PLATFORM (OIP)

**Version :** 0.3.0 — Lot 2, collecte Tor ponctuelle et contrôlée.

**Statut :** lot 0 et lot 1 validés par l'opérateur ; lot 2 implémenté, **103 tests locaux réussis**. Démarrage Docker/Tor réel et migration PostgreSQL du lot 2 à vérifier sur le poste opérateur.

## Accès rapide — Lot 2

Ce lot ajoute Tor isolé (`tor`), un collecteur manuel (`collector`), une validation explicite par source, les tables `crawl_jobs`, `source_observations`, `discovered_onions` et des routes API de consultation. Aucun crawl automatique : les liens découverts restent en attente. Le contenu brut des pages n'est pas conservé.

**Procédure complète et limites : [`docs/08-lot2-collecte-tor.md`](docs/08-lot2-collecte-tor.md).**

```bash
sudo docker compose --profile test run --build --rm tests
sudo docker compose up --build -d
sudo docker compose exec api alembic current  # 0003_tor_collection attendu
# Après approbation manuelle et activation via /api/v1/sources/{uuid}/collection/enable :
sudo docker compose --profile tor up --build -d tor
sudo docker compose logs --tail=100 tor  # attendre « Bootstrapped 100% »
sudo docker compose --profile tor run --rm --build -e OIP_TOR_COLLECTION_ENABLED=true collector SOURCE_UUID
```

**Important :** les commandes `collector` ne doivent cibler qu'un UUID de source accessible publiquement et explicitement autorisée. Aucun accès Tor réel n'a été effectué lors de la génération de ce paquet.

---

## Historique : documentation du lot 1


**Version :** 0.2.0 — Lot 1, gestion contrôlée des sources.

**Statut :** lot 0 validé sur le poste opérateur ; lot 1 implémenté et testé localement (78 tests). Redéploiement Docker lot 1 à vérifier sur le poste opérateur.

**Langue de la documentation :** français.

Plateforme de veille documentaire sur sources Onion publiques et explicitement autorisées. Cette livraison étend le registre des sources et sa gouvernance, sans aucun accès Tor. Elle **ne** découvre, ne visite, ne télécharge et ne classe aucun site à ce stade.

## Fonctionnalités présentes

- FastAPI avec `GET /api/health` et `GET /api/ready`.
- SQLAlchemy + Alembic : tables `onion_sources` et `audit_logs`.
- API du registre : GET/POST/PATCH/DELETE, approbation/révocation, activation/désactivation, restauration et historique, authentifiée par `X-API-Key`.
- Ajout manuel exigeant `authorization_confirmed=true` et une note descriptive d'autorisation.
- Validation syntaxique et checksum des racines `.onion` v3; aucun accès réseau.
- Journal d'audit des décisions, motifs obligatoires, réponse 409 sur doublon, filtres et pagination.
- Import JSON atomique (100 sources maximum), export CSV (500 maximum) avec neutralisation des formules de tableur.
- Migration Alembic `0002_source_lifecycle` compatible avec le lot 0 (test SQLite).
- PostgreSQL 17 et API sur réseau Docker interne (aucun port direct publié), avec passerelle Nginx non privilégiée exposée uniquement sur `127.0.0.1:8000`.
- Tests hors ligne : 78 tests réussis localement, dont 20 tests hérités du lot 0. Les tests Docker du lot 1 restent à exécuter par l'opérateur.

## Arborescence exacte — fichiers présents

```text
onion-intelligence-platform/
├── .dockerignore
├── .env.example
├── .gitignore
├── compose.yaml
├── README.md
├── infrastructure/
│   └── nginx/
│       └── default.conf
├── backend/
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── README.md
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       ├── 0001_bootstrap.py
│       └── 0002_source_lifecycle.py
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
│       ├── test_validation.py
│       ├── test_migration_upgrade.py
│       └── test_source_lifecycle.py
└── docs/
    ├── bootstrap-postgresql-preview.sql
    ├── 00-cadrage.md
    ├── 01-architecture.md
    ├── 02-modele-donnees.md
    ├── 03-plan-developpement.md
    ├── 04-validation.md
    ├── 05-etat-du-projet.md
    ├── 06-securite.md
    └── 07-lot1-gestion-sources.md
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

Au démarrage de `api`, `alembic upgrade head` applique les migrations à PostgreSQL **avant** le lancement d'Uvicorn. `api` attend que le `healthcheck` de `db` devienne sain. La passerelle locale `gateway` attend que l’API soit saine et relaie les requêtes HTTP vers le réseau privé. Si la migration échoue, le processus API ne démarre pas, et la passerelle ne devient pas opérationnelle.

Réponses attendues :

```json
{"status":"ok","service":"oip-api"}
{"status":"ready","database":"reachable"}
```

Inspecter les tables :

```bash
docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\\dt"'
docker compose logs --tail=100 api gateway
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

**Validation du lot 0 sur le poste de développement :** `20 passed, 1 warning in 1.15s` via Docker Compose. **Lot 1 : 78 tests passés localement ; exécution Docker sur le poste opérateur à faire.** Les routes `/api/health` et `/api/ready` renvoient `200` via Nginx, et PostgreSQL est `healthy`. Le test de migration automatisé valide SQLite; les migrations PostgreSQL ont démarré sans erreur dans les journaux du conteneur API. Voir `docs/04-validation.md`.

## Arrêt et conservation des données

```bash
docker compose down
```

La commande ci-dessus conserve le volume PostgreSQL. **Attention :** `docker compose down -v` détruit les données de la base locale; effectuer une sauvegarde avant toute suppression.

## Sécurité / limites actuelles

- **Local uniquement** : clé API partagée (pas encore de RBAC), docs OpenAPI non protégées, aucun reverse proxy TLS.
- **Aucun réseau Tor** : l'architecture Tor et les règles de sortie réseau doivent être développées et auditées avant toute collecte.
- Les données du registre sont limitées aux métadonnées administratives : URL v3, nom, description, catégorie, priorité et justificatifs de décision.
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
8. [`docs/07-lot1-gestion-sources.md`](docs/07-lot1-gestion-sources.md) — routes, déploiement et migration du lot 1.

## Git — lot 0 (historique de référence)

```bash
git init -b main  # uniquement si le dépôt n'existe pas déjà
# À l'issue du lot 0 :
git add -A
git diff --cached --check
git commit -m "chore: validate OIP infrastructure lot 0"
git tag -a v0.1.0-lot0 -m "OIP : lot 0 validé"
```

Le fichier `.env` n'est pas inclus dans l'archive et est exclu de Git par `.gitignore`.

## Correctif local du 22/10/2026 : exposition du port 8000

Le réseau `private` possède `internal: true`; sur certaines versions de Docker, un conteneur exclusivement connecté à ce réseau ne publie pas son port sur l'hôte malgré `ports:`. La solution est une passerelle Nginx non privilégiée sur deux réseaux : `ingress` standard pour le port hôte, `private` pour joindre l'API. Les conteneurs `api` et `db` restent connectés uniquement à `private`, sans publication directe de ports.

Après remplacement des fichiers, exécuter :

```bash
docker compose down              # SANS -v, pour conserver PostgreSQL
docker compose config            # vérifier la configuration
docker compose up --build -d
docker compose ps -a
docker compose logs --tail=80 api gateway
docker compose port gateway 8080 # attendu : 127.0.0.1:8000
curl --fail-with-body http://127.0.0.1:8000/api/health
curl --fail-with-body http://127.0.0.1:8000/api/ready
```

Cette architecture ne garantit pas l'absence de toutes les sorties réseau de `gateway`, connecté à `ingress`; limiter ses destinations sortantes via le pare-feu hôte pour une politique stricte. Le composant collecteur Tor n'existe pas encore et ne partage pas `ingress`. Le proxy ne rend pas l'API utilisable sur un réseau public : la liaison est strictement locale à `127.0.0.1` dans les conditions habituelles de Docker récent.


## Lot 1 — Mise à niveau du dépôt existant

L'archive contient les fichiers versionnés de la nouvelle livraison, mais **ni `.git`, ni `.env`**. Extraire sur le dépôt du lot 0 depuis une branche de fonctionnalité ; ne pas supprimer les volumes de base de données.

```bash
git switch -c feature/lot1-source-management
unzip -o /CHEMIN/OIP_lot1_sources_0.2.0.zip -d .
docker compose --profile test run --build --rm tests
docker compose up --build -d
curl -fsS http://127.0.0.1:8000/api/ready
git add -A
git diff --cached --check
git commit -m "feat: add source lifecycle and audit (lot 1)"
```

Pour la liste exhaustive des routes, les exemples d'import et la stratégie de migration : [`docs/07-lot1-gestion-sources.md`](docs/07-lot1-gestion-sources.md).
