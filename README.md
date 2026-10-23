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

## Documentation

| Document | Public | Contenu |
|---|---|---|
| **[Guide utilisateur](docs/guide-utilisateur.md)** | Opérateurs | Connexion, sources, collecte par clic, découvertes, alertes, exports et problèmes courants |
| [Installation et administration](docs/installation-administration.md) | Administrateurs | Installation, RBAC, sauvegardes, mises à jour, rotation et exploitation Tor |
| [Architecture et sécurité](docs/architecture-securite.md) | Équipe technique | Diagrammes, réseaux, contrôles, risques résiduels et limites de la collecte |
| [API et développement](docs/api-developpement.md) | Développeurs | API, tests, migrations, frontend et contributions |
| [Publication GitHub](docs/publication-github.md) | Mainteneurs | Nettoyage, inspection Git/historique, secrets, vérifications avant push |

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
