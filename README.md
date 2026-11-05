# Onion Intelligence Platform (OIP)

**Veille documentaire contrôlée sur des sources `.onion` explicitement autorisées.**
Version du code : **v1.0.0-rc2** · Interface locale · Python/FastAPI · PostgreSQL · Tor · React/TypeScript

OIP aide à enregistrer des sources Onion v3 approuvées, lancer **une collecte manuelle par source** depuis le dashboard, observer les changements, examiner les découvertes et consulter des signaux CTI, alertes et rapports. Les découvertes ne sont **jamais** explorées automatiquement.

> **Périmètre** — OIP est un outil de veille documentaire et non un scanner de masse. Utilisez-le uniquement sur des services accessibles publiquement avec une autorisation explicite. Une classification ou une alerte n'est pas une preuve d'activité illicite. La sécurité de Tor et des réseaux conteneurisés ne constitue pas une garantie d'anonymat absolu.

## Démarrage rapide

**Prérequis :** Linux, Docker Engine et Docker Compose v2. Le navigateur accède à OIP sur `127.0.0.1` uniquement.

```bash
# Sur un nouvel environnement seulement : préparer votre propre .env,
# avec un mot de passe PostgreSQL et une clé aléatoires distincts.
cp .env.example .env
# Modifier .env avant de démarrer : les placeholders sont interdits.
sudo docker compose up --build -d
curl -fsS http://127.0.0.1:8000/api/ready
```

Dans une installation existante, **conservez le `.env` et les volumes PostgreSQL** ; ne relancez pas l'initialisation de la base. Pour un accès opérateur :

```bash
sudo docker compose exec -T api \
  python -m app.security.manage_users create operator --role ADMIN --days 30
```

La commande affiche un jeton personnel **une seule fois**. Conservez-le hors du dépôt et collez-le dans l'écran de connexion à **http://127.0.0.1:8000/**. Pour un compte existant, utilisez `issue operator --days 30` au lieu de `create`.

Pour activer le traitement des **clics de collecte** (opération explicite, aucune planification automatique) :

```bash
sudo docker compose --profile tor up --build -d tor queue_worker
sudo docker compose logs --tail=30 tor queue_worker
```

Ouvrez **Sources Onion** : ajoutez une source autorisée (`ADMIN`), activez son autorisation de collecte, puis cliquez **▶ Collecter**. Consultez le statut `PENDING → RUNNING → COMPLETED / FAILED` et les observations.

## Développement M3 (hors production)

La branche M3 ajoute une **planification opt-in par source**, désactivée
par défaut, sous contrôle ADMIN, avec fenêtres UTC, expiration, budget
quotidien et audit des décisions. Le scheduler **n'effectue aucune requête
réseau** : il dépose uniquement des jobs en base, soumis aux contrôles M2.
Voir [M3 — Surveillance gouvernée](docs/m3-governed-scheduling.md).

**Ne pas activer sur OVH :** `0010_governed_schedules` requiert une sauvegarde
restaurée et des tests de concurrence PostgreSQL préalables. Le contrat Tor
reste à confirmer avant tout usage réel.

## M4-A — Exploration des observations (non déployé)

Une page **Observations** propose la recherche sur titres/descriptions conservés, des filtres historiques et une comparaison d’empreintes. La migration optionnelle de performance PostgreSQL `0011_observation_metadata_fts` est prévue **hors production** : ne pas la lancer sur OVH tant que la restauration hors site n’est pas validée. [Guide M4-A](docs/m4-observation-investigation.md).

## Documentation

**Durcissement M7-A (hors production)** : voir [modèle de menace et contrôles HTTP](docs/m7a-security-hardening.md). Les configurations Nginx et FastAPI mises à jour ne sont pas encore déployées sur OVH.

| Document | Public | Contenu |
|---|---|---|
| **[Guide utilisateur](docs/guide-utilisateur.md)** | Opérateurs | Connexion, sources, collecte par clic, découvertes, alertes, exports et problèmes courants |
| [Installation et administration](docs/installation-administration.md) | Administrateurs | Installation, RBAC, sauvegardes, mises à jour, rotation et exploitation Tor |
| [Architecture et sécurité](docs/architecture-securite.md) | Équipe technique | Diagrammes, réseaux, contrôles, risques résiduels et limites de la collecte |
| [API et développement](docs/api-developpement.md) | Développeurs | API, tests, migrations, frontend et contributions |
| [Publication GitHub](docs/publication-github.md) | Mainteneurs | Nettoyage, inspection Git/historique, secrets, vérifications avant push |

## M5-B (développement hors production)

La détection **optionnelle** de mentions explicites d'IOC (domaines, IP publiques, SHA-256) exige `OIP_IOC_EXTRACTION_ENABLED=yes` dans l'environnement du collecteur. Par défaut elle est désactivée. Les analystes disposent d'une revue à motifs codifiés ; aucune corrélation ou alerte malveillante ne découle automatiquement d'une simple mention. Voir [M5-B : candidats IOC et minimisation](docs/m5b-ioc-candidates.md). Cette version ne doit pas être migrée sur OVH sans recette PostgreSQL 17 et sauvegarde restaurable hors site.

## Qualité documentaire CTI (M5-C, hors production)

La vue M5-C combine une note explicable de *qualité des mentions* (distincte de la priorité humaine), des cooccurrences CVE/IOC acceptées sur la **même observation**, et un historique d’audit expurgé. Aucune mention ne confirme malveillance ou exploitation. Voir [la note technique M5-C](docs/m5c-documentary-quality.md). Aucun nouveau traitement réseau ni migration supplémentaire n’est nécessaire pour cette vue ; elle reste non déployée sur OVH.

## Validation

```bash
sudo bash scripts/validate-v1.sh --core     # tests backend, runtime, réseau et restauration temporaire
sudo bash scripts/validate-v1.sh --release  # + jeton nominatif, audits en ligne, frontend et Chromium
python3 scripts/verify-manifest.py          # empreintes de la distribution, hors fichiers locaux
python3 scripts/pre-push-audit.py           # inspection Git et historique, sans afficher les secrets
```

La validation ne visite **aucun service Onion réel**. Le test Playwright facultatif lié au bouton de collecte peut être ignoré : une recette manuelle approuvée reste nécessaire. `frontend/package-lock.json` doit être **versionné** après génération avec `npm install --package-lock-only --ignore-scripts` ; il n'est pas fourni dans l'archive RC2 d'origine.

**Gel d'implémentation :** ce nettoyage ne modifie pas les routes, les modèles, les migrations, les composants React ni le collecteur. L'état historique des versions et les comptes rendus de lots ont été retirés de la documentation active.

**Licence :** aucune licence open source n'est définie dans cette distribution. Choisissez-en explicitement une avant toute publication présentée comme open source ; publier du code sur GitHub n'accorde pas automatiquement un droit de réutilisation.

### Développement M5-A (hors production)

Le workflow de revue des références **CVE publiques** et la corrélation documentaire
sont décrits dans [M5-A — CTI publique gouvernée](docs/m5a-public-reference-triage.md).
La migration `0013_indicator_triage` n'est pas autorisée sur le VPS OVH avant
une restauration externe vérifiée et des tests PostgreSQL 17 dédiés.

## M6-A — Dossiers d'analyse (hors production)

L'espace **Dossiers** permet aux analystes d'associer un dossier à une alerte,
de l'assigner à un opérateur actif, d'enregistrer revue/escalade/clôture et
de consulter la chronologie des décisions. Le verrou de version empêche
l'écrasement silencieux des mises à jour concurrentes ; aucun extrait de
page ni commentaire libre n'est enregistré. Cette fonctionnalité ajoute la
migration additive `0015_analyst_cases`, **non appliquée sur OVH**. Voir
[le guide M6-A](docs/m6a-analyst-cases.md).

## Module expérimental M6-C (hors production)

Le module [Opérations analystes](docs/m6c-case-operations.md) ajoute des politiques
ADMIN explicitement approuvées, des brouillons locaux `NOT_SENT` et un rapport
agrégé sans extrait de source. Aucun transport externe n'est implémenté.
La migration `0017` ne doit pas être appliquée au VPS avant recette PostgreSQL 17
et restauration vérifiée.

## Sécurité des identités — lot M7-B2 (hors production)

La vue **Mes accès** permet à chaque opérateur nominatif de consulter les métadonnées de ses jetons (sans secret). Les administrateurs locaux disposent de commandes `issue --label` et `rotate` avec limite de cinq jetons actifs, ainsi que de la révocation et des protections M7-B1. Voir [Gouvernance des jetons M7-B2](docs/m7b2-token-governance.md). Ces nouveautés restent non déployées sur OVH jusqu'à la recette PostgreSQL et à une restauration vérifiée.
