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


## Livraison 0.2.0 — Lot 1 : registre et cycle de vie des sources

**État :** code réalisé, 78 tests locaux réussis, déploiement PostgreSQL/Docker lot 1 à vérifier par l'opérateur. Le jalon `v0.1.0-lot0` n'est pas modifié.

- Sources : GET individuel, PATCH sur métadonnées, filtrage et pagination ; actions séparées d'activation/désactivation, approbation/révocation, suppression logique et restauration.
- Audit : ajout `details` aux événements ; historisation des actions sans conservation des secrets ou corps de pages.
- Import atomique JSON (100 max), export CSV (500 max) avec protections formule tableur.
- Modèle : `is_active`, `priority`, `deleted_at`; migration Alembic `0002_source_lifecycle`.
- Sécurité : toutes les routes restent authentifiées par clé API; aucune action ne définit `collection_enabled=true` et aucune requête Tor n'est possible.
- Tests : 78 passed (tests FastAPI/SQLite + upgrade base Lot 0).
- À terminer : identités nominatives, rôles/RBAC et tests d'intégration PostgreSQL de la nouvelle migration.

**Décisions nouvelles :** suppression réversible sans restauration d'autorisation ; autorisation toujours explicite ; aucun fetch automatique ; approbation ne vaut pas activation de collecte.


## Livraison 0.3.0 — Lot 2 : collecte Tor contrôlée

**État :** code réalisé, 103 tests locaux réussis, tests Tor et déploiement Docker de ce lot **non exécutés** dans l'environnement de génération.

- Profil Compose `tor` séparé, services `tor` et `collector` désactivés par défaut.
- Conteneur `collector` uniquement sur réseaux internes `private` et `tor_proxy`.
- Collecte ponctuelle d'une racine Onion v3 autorisée via Tor SOCKS5, jamais de sortie réseau directe ni de suivi automatique des liens.
- Limites strictes : 256 KiB, MIME texte, 1 GET, aucun redirect, contenu non conservé.
- API d'autorisation d'une source (enable/disable) avec audit, lecture des observations/jobs/découvertes.
- Migration `0003_tor_collection`, nouvelles tables `crawl_jobs`, `source_observations`, `discovered_onions`.
- Tests locaux 103/103 : tests hérités et tests lot 2 avec collectes fictives.
- À faire : validation Docker Tor réel/PostgreSQL, RBAC, quotas temporels, rétention, classification de contenu sensible avant extension des collectes.


## Livraison 0.4.0 — Lot 3 : analyse et découverte contrôlée

**Date :** 23 octobre 2026. **État :** code implémenté, 113 tests locaux réussis (hors réseau), schéma Alembic SQLite sans dérive et SQL PostgreSQL généré. Déploiement PostgreSQL/Docker réel de ce lot à confirmer sur le poste opérateur.

- Extraction HTML/plaintext transitoire, effacement de script, normalisation, SHA-256 ; distinction première vue / inchangée / modifiée.
- Recherche de termes exacts de watchlist en mémoire, comptes et contributions au score de pertinence, pas d'extraits enregistrés.
- Détection checksum Onion v3 `LINK`, `TEXT` ou `BOTH`, 50 candidats maximum, file `PENDING` sans visite.
- Décision de revue `APPROVED` / `REJECTED` avec `reason` court, neutre et en anglais ; revue sans activation de collecte.
- Migration 0004, 3 tables nouvelles, 5 champs enrichis sur observations/découvertes, audit des opérations.
- RBAC, rétention, classification sensible et alertes restent hors périmètre du lot 3.

**Point de sécurité :** `APPROVED` sur une découverte ne transforme jamais la cible en source approuvée ni active. L'ancien module de gestion des sources reste le seul canal d'approbation.

Voir `docs/09-lot3-analyse-decouverte.md`.
