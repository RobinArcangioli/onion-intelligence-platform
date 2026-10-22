# Lot 4 — Classification documentaire et Cyber Threat Intelligence (OIP v0.5.0)

## 1. Portée réelle

Le lot 4 ajoute un classificateur **hors ligne et déterministe** pour les **observations de pages déjà autorisées**, des signaux CTI élémentaires et une vue de cooccurrence avec les watchlists. Les données sont dérivées uniquement du texte temporairement présent en mémoire pendant la collecte ponctuelle du lot 2/3.

Il **ne confirme ni incident ni attribution**, n'analyse pas les fichiers téléchargés, ne suit aucune découverte et ne modifie pas automatiquement la catégorie officielle d'une source. La collecte continue de nécessiter une source v3 activée, approuvée et une commande explicite sur le conteneur `collector`.

### Classification descriptive

- `NEWS`, `FORUM`, `DOCUMENT_SHARING`, `ONION_DIRECTORY`
- `CYBERCRIME_FORUM`, `RANSOMWARE_LEAK_SITE`, `SUSPECTED_DATA_LEAK`, `FRAUD_RELATED`
- `EXTREMIST_PROPAGANDA`, `SUSPECTED_CHILD_EXPLOITATION`

Les catégories sont **des suggestions heuristiques** et peuvent être erronées, particulièrement lorsqu'une actualité *parle* d'un phénomène sans que la source le pratique. La confiance de 0 à 75 est la **force d'un signal lexical**, pas une probabilité calibrée d'exactitude. Plusieurs catégories peuvent correspondre à une observation. Aucune catégorie ne provoque de navigation supplémentaire.

Les règles sont versionnées dans `backend/app/classifiers/rules.py`, avec leurs codes explicables. Ce lot ne comprend pas d'éditeur de taxonomie à chaud : toute modification des règles nécessite une nouvelle version déployée. La catégorie `UNKNOWN` correspond dans cette version à **l'absence de suggestions** plutôt qu'à une ligne artificiellement produite.

### Signaux de cybermenaces

- `PUBLIC_CVE_REFERENCE` : forme textuelle d'un identifiant CVE public, non vérifiée auprès d'un registre externe ; état `OBSERVED_REFERENCE`.
- `RANSOMWARE_CLAIM`, `DATA_LEAK_CLAIM`, `ACCESS_SALE_CLAIM` : signalement de propos publiés, état `OBSERVED_CLAIM` ; **jamais** automatiquement marqué `CONFIRMED`.

Aucun identifiant de connexion, secret, extrait de fuite, IP ou adresse personnelle ne doit être extrait ou enregistré par ce module. Seuls les CVE publics peuvent figurer comme `public_reference`. Les indicateurs de revendication ont une référence vide et portent seulement un type, un code d'indice et l'identifiant de l'observation/source.

### Corrélation avec les watchlists

La route `/api/v1/cti/correlations` rapproche uniquement une **cooccurrence dans la même observation** entre une correspondance de watchlist et un indicateur CTI. Elle renvoie des UUID, des compteurs et un score de pertinence **distinct** de la confiance de classification. Elle ne divulgue aucun texte de règle et ne prétend pas qu'une entreprise a été réellement compromise.

## 2. Sécurité et minimisation

- Aucun nouvel accès réseau, aucune exécution JavaScript, aucun téléchargement ou suivi de liens ; le navigateur et le collecteur existants ne changent pas de politique réseau.
- Extraction et classification en mémoire ; `ClassificationResult` et `ThreatIndicator` ne stockent que des codes de règles, des statuts, des niveaux de confiance et éventuellement un CVE public.
- Si le texte laisse soupçonner la catégorie `SUSPECTED_CHILD_EXPLOITATION`, le collecteur **désactive la prochaine collecte**, n'enregistre ni titre ni description ni découverte ni correspondance ni indice CTI non nécessaire, et conserve uniquement une classification à examiner. Cela peut produire des faux positifs, notamment sur des articles d'information. Il faut une vérification humaine appropriée avant toute réactivation.
- `EXTREMIST_PROPAGANDA` requiert également une revue, mais ne désactive pas systématiquement la source.
- La revue d'une catégorie `ACCEPTED`/`REJECTED` n'est pas une confirmation d'un acte, d'une compromission ou d'une identité. Elle ne réactive pas la collecte.
- Les valeurs `reason` des actions sont minimales, en anglais, par défaut `Manual check` (contrainte backend : 10 caractères minimum). Elles sont conservées dans l'audit local, pas envoyées à la source `.onion`.
- Le système n'utilise pas automatiquement les informations publiées pour télécharger des données, vérifier des identifiants ou accéder à un service privé.

## 3. API authentifiée (X-API-Key)

| Méthode | Route | Fonction |
|---|---|---|
| GET | `/api/v1/cti/taxonomy` | Catégories/règles versionnées, sans mots-clés sensibles |
| GET | `/api/v1/cti/classifications` | Liste paginée, filtres `source_id`, `observation_id`, `category`, `review_status` |
| GET | `/api/v1/cti/classifications/{id}` | Détail de suggestion |
| POST | `/api/v1/cti/classifications/{id}/review` | Revue humaine unique, auditée |
| GET | `/api/v1/cti/indicators` | Références et revendications observées, filtres |
| GET | `/api/v1/cti/indicators/{id}` | Détail d'indicateur |
| GET | `/api/v1/cti/correlations` | Cooccurrences indicateur/watchlist, non probantes |

**Exemple sans exposer la clé dans la commande :**

```bash
cd ~/onion-intelligence-platform
OIP_KEY=$(sed -n 's/^OIP_API_KEY=//p' .env)
curl -fsS -H "X-API-Key: $OIP_KEY" http://127.0.0.1:8000/api/v1/cti/taxonomy
curl -fsS -H "X-API-Key: $OIP_KEY" http://127.0.0.1:8000/api/v1/cti/classifications
curl -fsS -H "X-API-Key: $OIP_KEY" http://127.0.0.1:8000/api/v1/cti/indicators
curl -fsS -H "X-API-Key: $OIP_KEY" http://127.0.0.1:8000/api/v1/cti/correlations
```

Revue d'une suggestion existante (substituer le vrai UUID) :

```bash
curl -fsS -X POST \
  'http://127.0.0.1:8000/api/v1/cti/classifications/UUID/review' \
  -H "X-API-Key: $OIP_KEY" -H 'Content-Type: application/json' \
  -d '{"decision":"ACCEPTED","reason":"Manual check"}'
```

Après utilisation, effacez la clé de votre session avec `unset OIP_KEY`.

> `ACCEPTED` atteste uniquement la décision d'un opérateur concernant une catégorie documentaire, **pas** la véracité de la publication. Les UUID et résultats demeurent locaux.

## 4. Installation dans le dépôt existant

**Ne pas supprimer `.env`, les volumes Docker ou `.git`.** Le ZIP superpose les fichiers versionnés uniquement.

```bash
cd ~/onion-intelligence-platform
git switch -c feature/lot4-cti-classification
unzip -o ~/Téléchargements/OIP_lot4_classification_CTI_v0.5.0.zip -d .
sudo docker compose config --quiet
sudo docker compose --profile test run --build --rm tests
sudo docker compose up --build -d
sudo docker compose exec api alembic current
curl -fsS http://127.0.0.1:8000/api/ready
```

**Migration attendue :** `0005_cti_classification (head)`.

Aucun changement de variable d'environnement n'est requis pour ce lot ; Tor reste en profil `tor`, et le collecteur manuel reste désactivé par défaut. Les précédentes observations ne sont pas « rétro-classifiées » : seules les nouvelles collectes produisent des résultats CTI. Aucun service Tor ne doit être lancé pour tester le lot 4.

### Git après validation

```bash
git add -A
git diff --cached --check
git commit -m "feat: add offline classification and CTI signals - lot 4"
git tag -a v0.5.0-lot4 -m "OIP lot 4 validated"
```

## 5. Validation et limites

- Tests générés hors réseau avec des pages fictives, sans aucune visite Onion ; rapports de tests dans `docs/04-validation.md`.
- Migration `0004 -> 0005` testée sur SQLite peuplé, sans perte d'observations ; schéma ORM/Alembic contrôlé sur SQLite.
- SQL PostgreSQL généré hors ligne, mais migration sur PostgreSQL 17 réelle et lancement Docker **non exécutés ici**.
- Les règles sont conservatrices mais limitées, avec faux positifs et faux négatifs. Aucune recherche NLP ni validation externe de CVE/incident.
- Le signalement des cas particulièrement sensibles nécessite un processus légal et humain adapté. Aucun stockage de matériel illicite n'est prévu.
- Pas de déduplication inter-observations des revendications, pas d'alertes, de rapports planifiés ou de RBAC nominatif ; lots ultérieurs.
- Pas de preuves de classification automatiquement conservées sous forme d'extraits textuels, volontairement, par minimisation.

## 6. Prochaine étape

Lot 5 : alertes dédupliquées et rapports JSON/CSV, avec une séparation explicite entre signal observé, revendication non vérifiée, catégorie suggérée et information publiquement confirmée par des sources externes fiables.
