# 09 — Lot 3 : extraction, analyse locale et découvertes contrôlées (v0.4.0)

## Périmètre livré

La collecte conserve strictement les garde-fous du lot 2 : 1 GET explicite par job sur la racine Onion v3 autorisée, uniquement via Tor SOCKS5, redirects et médias refusés, 256 Kio maximum, collecte désactivée par défaut, jamais de visite des découvertes.

**Nouveautés :**

- Extraction HTML et texte brut (en mémoire) ; scripts, feuilles de style, formulaires, navigation et éléments actifs éliminés avant analyse.
- Adresses Onion v3 repérées dans les `href` ET dans le texte nettoyé ; checksum obligatoire, 50 candidats max / observation, jamais explorés ; statut `PENDING`, type de preuve `LINK`, `TEXT` ou `BOTH`.
- Watchlists et expressions exactes : création, liste, activation/désactivation. Expressions littérales uniquement (pas de regex utilisateur), 200 règles maximum, poids entiers de 1 à 30 ; borne de 20 occurrences par règle.
- Correspondances analysées localement : seules la règle, le nombre d'occurrences et la contribution au score sont conservés en base ; pas d'extrait textuel.
- Score de pertinence **non probabiliste**, 0 à 100 : `min(100, sum(min(occurrences, 3) * weight))` sur les règles actives. Il ne mesure ni dangerosité ni véracité.
- Empreintes textuelles SHA-256 avec statuts `FIRST_SEEN`, `UNCHANGED`, `MODIFIED`. Les observations anciennes sont marquées `UNKNOWN` à la migration.
- Revue manuelle d'une découverte en `APPROVED` / `REJECTED`, avec audit. **APPROVED n'insère PAS une source autorisée et n'active aucune collecte.** Pour collecter une adresse, il faut toujours l'enregistrer et l'approuver via le circuit de gestion des sources existant.
- API authentifiée avec la clé existante ; aucun lancement Tor via HTTP.

## Installation sur un dépôt lot 2

Depuis la branche de fonctionnalité Git choisie, à la racine du projet, extraire le ZIP livré :

```bash
unzip -o ~/Téléchargements/OIP_lot3_analyse_decouverte_v0.4.0.zip -d .
sudo docker compose config --quiet
sudo docker compose --profile test run --build --rm tests
sudo docker compose up --build -d
sudo docker compose exec api alembic current
curl -fsS http://127.0.0.1:8000/api/ready
```

Migration attendue : `0004_intelligence` ; migration lancée automatiquement au démarrage de l'API. Les données et autorisations du lot 2 restent intactes ; l'ancien score est initialisé à 0 et le statut de changement à `UNKNOWN`.

### Exemple de configuration sans visite réseau

La clé API réside dans `.env` et doit rester privée :

```bash
read -rsp 'OIP API key: ' OIP_KEY; echo
# La variable OIP_KEY est définie dans ce shell uniquement.

curl -fsS -X POST http://127.0.0.1:8000/api/v1/watchlists \
  -H "X-API-Key: $OIP_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"Company watch"}'
```

Noter l'UUID de la watchlist renvoyée, puis :

```bash
WATCHLIST_UUID='UUID_FROM_RESPONSE'
curl -fsS -X POST "http://127.0.0.1:8000/api/v1/watchlists/$WATCHLIST_UUID/rules" \
  -H "X-API-Key: $OIP_KEY" -H 'Content-Type: application/json' \
  -d '{"phrase":"Example Corp","weight":15}'
```

Ces opérations ne contactent aucun service externe. Les règles s'appliquent aux **prochaines** collectes autorisées, pas rétroactivement aux observations historiques. Pour lancer une collecte, voir `08-lot2-collecte-tor.md` et ne cibler qu'une source autorisée.

### Résultats

```bash
curl -fsS -H "X-API-Key: $OIP_KEY" \
  'http://127.0.0.1:8000/api/v1/collection/observations?limit=20'

OBSERVATION_UUID='UUID_FROM_RESPONSE'
curl -fsS -H "X-API-Key: $OIP_KEY" \
  "http://127.0.0.1:8000/api/v1/collection/observations/$OBSERVATION_UUID/analysis"

curl -fsS -H "X-API-Key: $OIP_KEY" \
  'http://127.0.0.1:8000/api/v1/collection/discoveries?status=PENDING'
```

### Revue d'un candidat sans autoriser de collecte

```bash
DISCOVERY_UUID='UUID_FROM_RESPONSE'
curl -fsS -X POST \
  "http://127.0.0.1:8000/api/v1/collection/discoveries/$DISCOVERY_UUID/review" \
  -H "X-API-Key: $OIP_KEY" -H 'Content-Type: application/json' \
  -d '{"decision":"REJECTED","reason":"Manual check"}'

unset OIP_KEY
```

`reason` est une note locale d'audit, non transmise au service Onion ; minimum 10 caractères. Les journaux peuvent cependant contenir des identifiants techniques et doivent être protégés.

## Sécurité et limitations

- Le collecteur ne stocke **aucun corps HTML**, texte complet de page, contexte textuel de correspondance, média ou archive. Titre, description, URL de découverte, empreinte et compteurs sont conservés et peuvent néanmoins contenir des informations à protéger.
- L'identité du service Onion n'est pas vérifiée au-delà de la validité syntaxique/checksum de l'adresse et du protocole utilisé ; une adresse détectée n'est pas une preuve de disponibilité ou de légitimité.
- Les scores sont déterministes et ne classent pas la gravité, l'illégalité ou la fiabilité d'une affirmation. Pas de NLP ou de taxonomie sensible à ce stade.
- Les règles sont évaluées pendant la collecte ; aucun retraitement rétroactif. Des collectes simultanées sur une même source ne sont pas sérialisées ; un planificateur avec verrous et quotas est requis avant augmentation du débit.
- Pas encore de RBAC nominatif, politique de rétention automatique, purge des découvertes, alertes, rapports, dashboard ni multi-pages. Les expressions des règles sont visibles par les détenteurs de la clé API.
- L'extraction textuelle dépend de l'encodage et de la structure HTML ; les pages dynamiques ne sont jamais exécutées.
- Environnement de génération : **113 tests pytest hors ligne**, migration 0003→0004 contrôlée sur SQLite, schéma Alembic contrôlé, SQL PostgreSQL généré. **Aucun Docker/PostgreSQL réel ni collecte Tor réelle effectués dans cet environnement pour ce lot.**

## Tests

```bash
sudo docker compose --profile test run --build --rm tests
sudo docker compose exec api alembic current
sudo docker compose exec api alembic check
```

La validation sur le poste opérateur est distincte des tests hors ligne. Ne jamais exécuter `docker compose down -v` pour mettre à niveau ; cette option supprimerait le volume de données.

## Livrables ajoutés

- `backend/app/analyzers/{__init__.py,keywords.py}`
- `backend/app/api/intelligence.py`
- `backend/app/models/intelligence.py`
- `backend/app/schemas/intelligence.py`
- `backend/alembic/versions/0004_intelligence.py`
- `backend/tests/test_intelligence_lot3.py`
- `backend/tests/test_migration_lot3_upgrade.py`

Fichiers modifiés : extracteur/runner, modèles d'observation, réponses API, routes découvertes, `app/main.py`, `backend/pyproject.toml`, tests de migration et documentation.

## Étape suivante

Poursuivre les protections (débit global, sérialisation par source, politique de rétention) puis classifier prudemment les observations et générer les alertes non intrusives. Aucun ajout automatique de source ni navigation multi-pages sans contrôle préalable.


oip_lnE5ParwWZDZ2urORa8jtGhTxdc8iADM6onZou5MFE8
