# 04 — Validation réellement effectuée

## Périmètre du banc d'essai

- Hôte d'exécution : Python 3.13.5; FastAPI 0.128.2; SQLAlchemy 2.0.50; Alembic 1.18.4; pytest 9.0.2.
- Base de tests : SQLite en mémoire + un fichier SQLite temporaire pour Alembic.
- Aucun accès Tor. Aucune requête à un site réel. Le seul hôte `.onion` des tests est synthétique.
- Docker absent de la machine de génération; images, Compose et vrai PostgreSQL ne sont **pas** exécutés ici.

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

## Vérifications indispensables sur poste équipé Docker

```bash
cp .env.example .env
# Remplacer les valeurs par des secrets aléatoires de longueur suffisante (voir README).
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1:8000/api/ready
docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\\dt"'
docker compose --profile test run --build --rm tests
```

Attendu : base saine, migrations à jour, trois tables SQL visibles (`alembic_version`, `onion_sources`, `audit_logs`), statut 200 des deux endpoints, tests verts. Tant que ces commandes ne sont pas exécutées sur une machine avec Docker, ce sont des **critères d'acceptation**, pas des résultats obtenus.

## Réserves

- La migration Alembic est testée contre SQLite; certaines spécificités PostgreSQL demandent un test d'intégration réel.
- Le code d'intégration Docker n'est pas exécuté dans ce banc d'essai.
- Le registre ne teste pas la disponibilité d'un service Onion.
