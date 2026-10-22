# 05 — État du projet (versionnable)

**Date d'établissement :** 22 octobre 2026

**Version :** v0.1.0 / Lot 0

**Phase :** première implémentation du socle local, sans Tor

## Fonctionnalités implémentées

- Dépôt et Dockerfile multi-stage (`runtime` + `test`).
- Fichier Docker Compose PostgreSQL 17 + API FastAPI + profil tests.
- Configuration par environnement, clé API et validation de longueur.
- Endpoints `/api/health`, `/api/ready`.
- Endpoints authentifiés `GET/POST /api/v1/sources`.
- Validateur strict Onion v3 (racine, Base32, checksum SHA3-256, version).
- Migrations Alembic `0001_bootstrap` créant `onion_sources` et `audit_logs`.
- Historique d'audit minimal pour les ajouts manuels; refus doublon SQL.
- Suite de tests hors ligne FastAPI + SQLite + migration SQLite.
- Spécification des 20 tables cibles, de l'architecture cible et des lots suivants.

## Fonctionnalités testées

- Suite de **20 tests réussis** (`20 passed in 1.69s`) exécutée localement hors conteneur sous Python 3.13.5.
- Compilation Python (`compileall`) réussie et migration SQLite réussie (suite de tests).
- SQL DDL PostgreSQL généré hors connexion via Alembic (43 lignes, `docs/bootstrap-postgresql-preview.sql`).
- YAML Compose chargé avec succès via PyYAML (vérification syntaxique de base, pas `docker compose config`).
- Wheel Python construit avec succès hors réseau; `alembic upgrade head` puis `alembic check` sur SQLite temporaire : sorties 0 et 0, pas de drift détecté.
- À la génération initiale : Docker/PostgreSQL non testés. Ils ont ensuite été validés sur le poste opérateur (voir résultats ci-dessous). Tor et frontend restent non implémentés.

## Prochaine étape

1. Continuer les vérifications d’intégration (persistance, contraintes et migrations sur PostgreSQL).
2. Commencer le lot 1 : RBAC, évolution du modèle sources, contrôle d'autorisation révocable et endpoints CRUD complets.
3. Préparer, sans activer, les tests de confinement réseau qui conditionneront le lot Tor.

## Problèmes connus et dette technique

- Docker indisponible dans l’environnement de génération initiale; validation des services confirmée ultérieurement sur le poste de développement.
- Le modèle initial ne contient que deux des tables cibles; le reste est **documenté**, pas implémenté.
- Clé API partagée : pas d'identité nominative; pas de suppression ni modification des sources.
- Dépendances Python bornées mais pas verrouillées par hash, image PostgreSQL non épinglée par digest.
- Migrations automatiquement lancées au démarrage du conteneur API en développement; un job de migration indépendant sera requis pour un déploiement multi-réplique.
- Aucune donnée texte, page ou observation n'est encore collectée.

## Journal de décisions (ADR simplifié)

| ID | Décision | Motif |
|---|---|---|
| ADR-001 | API monolithique modulaire FastAPI | MVP simple, facile à tester et refactoriser |
| ADR-002 | SQLAlchemy synchrone, PostgreSQL | Transactions administratives et faible trafic initial |
| ADR-003 | Aucune sortie réseau Tor au lot 0 | Valider les fondations puis les contrôles de sécurité |
| ADR-004 | `.onion` v3 root only | Périmètre clair, rejet simple des URLs arbitraires |
| ADR-005 | Clé API temporaire + écoute locale | Test de bout en bout avec moindre surface exposée |
| ADR-006 | SQLite dans les tests unitaires, PG dans Compose | Tests rapides sans ressources réseau; validation PG séparée obligatoire |
| ADR-007 | Découvertes en attente de revue humaine | Aucune exploration non autorisée |

## Validation sur poste opérateur — 22 octobre 2026

**Lot 0 : VALIDÉ pour le développement local.** Les preuves suivantes ont été communiquées par l'opérateur :

- Images `api` et `tests` construites avec Docker Compose.
- PostgreSQL 17 démarré avec statut `healthy`.
- Migration Alembic initialisée sans erreur dans les journaux API.
- Passerelle Nginx ajoutée sur `ingress` + `private`, les services `api` et `db` étant sur `private` uniquement.
- `GET /api/health` : réponse HTTP 200 avec JSON attendu.
- `GET /api/ready` : réponse HTTP 200 avec `database=reachable`.
- Exécution de la suite Docker : **20 tests réussis, 1 avertissement en 1,15 seconde**.

**Dette technique conservée :** avertissement `StarletteDeprecationWarning` relatif au client de test HTTPX ; aucune vérification d'accès Tor ; pas encore de test d'intégration automatisé contre PostgreSQL réel.

La documentation de lot 0 peut être enregistrée dans Git. Le tag prévu est `v0.1.0-lot0`.
