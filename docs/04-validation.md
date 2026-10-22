# 04 — Validation réellement effectuée

## Périmètre du banc d'essai

- Hôte d'exécution : Python 3.13.5; FastAPI 0.128.2; SQLAlchemy 2.0.50; Alembic 1.18.4; pytest 9.0.2.
- Base de tests : SQLite en mémoire + un fichier SQLite temporaire pour Alembic.
- Aucun accès Tor. Aucune requête à un site réel. Le seul hôte `.onion` des tests est synthétique.
- Docker absent de la machine de génération initiale; validation Docker/PostgreSQL réalisée ensuite par l'opérateur sur son poste Linux, voir ci-dessous.

## Commande exécutée

```bash
cd backend
python -m pytest -q -p no:cacheprovider
```

## Résultats

**Résultat effectivement obtenu :** `20 passed in 1.69s` sous Python 3.13.5 (exécution sans Docker et sans Tor). Les vérifications comprennent :

- liveness et readiness de l'API, y compris simulation de panne SQL et réponse 503;
- refus des clés API absentes ou incorrectes;
- ajout manuel, lecture paginée, détection des doublons et vérification d'un enregistrement d'audit;
- confirmation explicite d'autorisation et rejets des URL non Onion ou malformées;
- validation checksum Onion v3 et contrôle du contrat OpenAPI;
- migration Alembic sur un fichier SQLite éphémère.

Autres commandes réellement exécutées :

```bash
python -m compileall -q app alembic tests
OIP_DATABASE_URL='postgresql+psycopg://oip:oip_dev@db:5432/oip' python -m alembic -c alembic.ini upgrade head --sql
```

La compilation Python s'est achevée sans erreur. La génération SQL **hors connexion** PostgreSQL a produit le fichier `docs/bootstrap-postgresql-preview.sql` (43 lignes), sans se connecter à PostgreSQL. La construction du wheel Python `0.1.0` (`pip wheel --no-deps --no-build-isolation .`) a réussi. Sur une base SQLite temporaire, `alembic upgrade head` **puis** `alembic check` ont retourné le code `0`, sans divergence détectée entre migrations et modèles ORM. Le fichier `compose.yaml` a été chargé avec succès via PyYAML : services `db`, `api`, `tests` et réseau `private` déclaré `internal: true`. **Cela ne remplace pas** `docker compose config` ni un démarrage réel. Les tests doivent être relancés après tout changement de code.

## Validation d'intégration par l'opérateur — 22 octobre 2026

Résultats transmis depuis le poste de développement Linux :

- `docker compose up --build -d` : images construites; PostgreSQL 17 `healthy`; API démarrée.
- Journaux `api` : Alembic `PostgresqlImpl`, puis `Application startup complete` et Uvicorn sur `0.0.0.0:8000`.
- Passerelle Nginx ajoutée après correction réseau ; `GET /api/health` : `200`, `{"status":"ok","service":"oip-api"}`.
- `GET /api/ready` : `200`, `{"status":"ready","database":"reachable"}`.
- `docker compose --profile test run --build --rm tests` : **`20 passed, 1 warning in 1.15s`**.
- Avertissement connu non bloquant : `StarletteDeprecationWarning` concernant `httpx` / `starlette.testclient`; à réexaminer lors de la mise à jour des dépendances.

Ces preuves valident le lot 0 pour un développement local. Elles ne valident pas l'isolement réseau nécessaire à Tor ni le déploiement de production.

## Commandes de vérification réutilisables

```bash
# Conserver le .env local existant ; voir README pour une nouvelle installation.
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1:8000/api/ready
docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\\dt"'
docker compose --profile test run --build --rm tests
```

Attendu lors des prochaines vérifications : base saine, migrations à jour, trois tables SQL visibles (`alembic_version`, `onion_sources`, `audit_logs`), statut 200 des deux endpoints et tests verts. La liste SQL des trois tables et les contrôles réseau détaillés restent à vérifier explicitement sur le poste.

## Réserves

- La migration Alembic est testée contre SQLite; certaines spécificités PostgreSQL demandent un test d'intégration réel.
- Le code Docker a été exécuté sur le poste de l’opérateur, mais pas dans l’environnement de génération de cette archive.
- Le registre ne teste pas la disponibilité d'un service Onion.
