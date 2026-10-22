# 03 — Plan de développement incrémental

Le mot « validé » exige des tests réellement exécutés, pas seulement un code écrit.

## Lot 0 — Fondations locales (livré dans cette archive)

- **Objectif :** dépôt, API, base, migrations, contrôle d'accès provisoire, tests hors ligne.
- **Composants :** Compose, PostgreSQL, FastAPI, SQLAlchemy, Alembic, registre manuel.
- **Fichiers :** `compose.yaml`, `backend/Dockerfile`, `backend/app/{main.py,api/*,db/*,models/*,schemas/*,security/*}`, `backend/alembic/*`, `backend/tests/*`.
- **Dépendances :** Python 3.12, Docker Compose pour validation PostgreSQL, aucune dépendance Tor.
- **Tests :** endpoints vivant/prêt, autorisation par clé, validation v3, insert/list/doublon/audit, migration SQLite, vérification Docker manuelle.
- **Acceptation :** `GET /api/ready` 200 avec PostgreSQL Docker, création SQL et audit, aucun fetch réseau; résultats consignés.

## Lot 1 — Gouvernance des sources et RBAC (registre livré ; RBAC restant)

- **Objectif :** éditeur de sources, désactivation, import/export, rôles utilisateurs, audit nominatif, autorisations revocables.
- **Composants :** services et dépôts sources, authentification + rôles, API.
- **Fichiers envisagés :** `backend/app/models/user.py`, `roles.py`, `backend/app/api/auth.py`, `backend/app/api/source_management.py`, nouvelles migrations.
- **Dépendances :** lot 0 et politique de gestion des identités.
- **Implémenté en 0.2.0 :** gestion CRUD, suppression logique, décisions d'autorisation, audit non nominatif, import JSON et export CSV, tests SQLite.
- **Restant :** comptes séparés, RBAC, audit nominatif, politique de révocation des sessions/clefs.
- **Tests :** 78 tests locaux réussis (API, validation, filtres, migration SQLite); tests identités 401/403 et PostgreSQL réels restant.
- **Acceptation :** aucune opération administrative sensible sans identité autorisée; décisions traçables.

## Lot 2 — Connectivité Tor sous garde-fous

- **Objectif :** vérification réseau d'une source approuvée, Tor uniquement, sans récupération sensible.
- **Composants :** gateway Tor, conteneur crawler isolé, liste d'autorisation, garde egress.
- **Fichiers envisagés :** `infrastructure/tor/torrc`, `backend/app/crawler/transport.py`, `backend/app/security/scope_policy.py`, Compose réseau isolé.
- **Dépendances :** gouvernance / politique d'autorisation, firewall Docker/hôte étudié.
- **Tests :** proxy absent => échec fermé; aucune requête HTTP directe; résolution DNS distante, timeout, URL hors scope, redirect bloquée, faux serveur local.
- **Acceptation :** aucune sortie réseau autre que Tor démontrée par tests et inspection réseau; environnement Tor réel vérifié à part.

## Lot 3 — Collecte et extraction HTML

- **Objectif :** collecter des pages textuelles autorisées avec quotas stricts et historisation.
- **Composants :** transport HTTP, parseur HTML, jobs, observations, empreintes.
- **Fichiers envisagés :** `backend/app/crawler/collector.py`, `backend/app/extractors/html.py`, `backend/app/workers/scheduler.py`, migrations pages/jobs/observations.
- **Dépendances :** lot 2 et règles de gestion des contenus sensibles.
- **Tests :** fixtures HTML sans réseau, limites bytes/durée/page, MIME refusé, scripts ignorés, déduplication, annulation et reprise.
- **Acceptation :** seule une source explicitement autorisée peut être consultée; données textuelles bornées et traçables.

## Lot 4 — Découverte, pertinence et CTI

- **Objectif :** candidats `.onion` non visités, validation humaine, watchlists, scoring explicable, classification prudente.
- **Composants :** discovery, scoring, classification, threat indicators.
- **Fichiers envisagés :** `backend/app/discovery/*`, `backend/app/scoring/*`, `backend/app/analyzers/*`, `backend/app/classifiers/*`, migrations correspondantes.
- **Dépendances :** lot 3, taxonomie et règles versionnées.
- **Tests :** URLs v3 extraites, aucun auto-follow, déduplication, provenance, scores déterministes, confiance indépendante, catégories sensibles en quarantaine.
- **Acceptation :** toutes les découvertes restent PENDING tant que non revues; scores compréhensibles et auditables.

## Lot 5 — Alertes et rapports

- **Objectif :** alertes non dupliquées, suivi des statuts, exports JSON/CSV vérifiables.
- **Composants :** alert engine, reports, filtres API.
- **Fichiers envisagés :** `backend/app/alerts/*`, `backend/app/reports/*`, `backend/app/api/alerts.py`, `reports.py`, migrations.
- **Dépendances :** lot 4.
- **Tests :** même événement => une alerte; filtrage dates/entités; export sans secrets; références et limites explicites.
- **Acceptation :** une observation mène à une alerte et à un rapport traçables sans convertir une allégation en fait avéré.

## Lot 6 — Dashboard et exploitation

- **Objectif :** UI complète avec vue générale, sources, découvertes, recherche, watchlists, alertes, rapports.
- **Composants :** React + TypeScript, composants visuels, API versionnée, scripts de déploiement.
- **Fichiers envisagés :** `frontend/package.json`, `frontend/src/*`, `frontend/Dockerfile`, guides.
- **Dépendances :** APIs stabilisées des lots 1–5.
- **Tests :** parcours utilisateur, auth, erreurs réseau, ergonomie responsive, pagination, contrôles de sécurité UI.
- **Acceptation :** tous les écrans affichent de vraies données, aucun tableau simulé ni donnée inventée.

## Gouvernance des livraisons

Chaque lot doit mettre à jour `docs/04-validation.md` et `docs/05-etat-du-projet.md` avec les fichiers, tests réellement exécutés, commandes, limites et prochaine étape. Tout changement de schéma nécessite une migration, des tests de compatibilité et une procédure de rollback documentée.


## Avancement au 22/10/2026

- Lot 0 : validé sur le poste opérateur (20 tests Docker).
- Lot 1 : déclaré validé par l'opérateur.
- Lot 2 : collecteur Tor manuel, tests locaux réussis ; **à valider sur le poste opérateur**. Détails : `docs/08-lot2-collecte-tor.md`.
- Prochaines phases : navigation interne autorisée avec quotas, politique de rétention, classification/alertes, dashboard.
