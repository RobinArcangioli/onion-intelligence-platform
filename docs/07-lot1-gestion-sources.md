# Lot 1 — Gouvernance du registre Onion (livraison 0.2.0)

## Périmètre livré

Cette livraison améliore le registre existant **sans activer Tor** et **sans toucher aux fichiers `.env` ni au volume PostgreSQL**.

- GET liste filtrable (`q`, `category`, `approved`, `active`, `priority`) et paginée (`limit`, `offset`).
- GET par UUID; PATCH sur `name`, `description`, `category`, `priority` avec justification.
- Activation/désactivation administrative d'une source, sans pouvoir activer la collecte.
- Révocation et renouvellement explicite d'autorisation (note obligatoire à l'approbation).
- Suppression logique et restauration **toujours désactivée et non autorisée**, à revalider séparément.
- Historique audit append-only des actions, horodatages et motifs (sans clé API, sans texte collecté).
- Import de 1 à 100 sources en JSON, atomique, avec validation de chaque autorisation.
- Export CSV borné à 500 sources, hors ressources supprimées, sans notes d'autorisation; cellules neutralisées contre les formules de tableur.
- Validation v3 stricte inchangée, rejet des colonnes sensibles dans les modifications (`collection_enabled`, `approved_for_collection`, URL canonique).

## Installation depuis le lot 0

À la racine du dépôt existant (lot 0 déjà committé) :

```bash
git switch -c feature/lot1-source-management
unzip -o /CHEMIN/OIP_lot1_sources_0.2.0.zip -d .
git diff --check
docker compose --profile test run --build --rm tests
docker compose up --build -d
docker compose ps -a
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/ready
docker compose exec api alembic current
```

Ne **pas** remplacer `.env`, ne **pas** utiliser `docker compose down -v`. Le conteneur API applique la migration `0002_source_lifecycle` au démarrage. Pour une installation contenant des données importantes, effectuer une sauvegarde PostgreSQL avant la mise à jour.

## Routes et requêtes

Toutes les routes du registre exigent `X-API-Key`. Aucun compte nominatif n'est encore disponible.

| Méthode | Route | Corps / usage |
|---|---|---|
| GET | `/api/v1/sources` | `q`, `category`, `approved`, `active`, `priority`, `limit`, `offset` |
| GET | `/api/v1/sources/{uuid}` | Consultation |
| POST | `/api/v1/sources` | `url`, `name`, `authorization_confirmed:true`, `authorization_note`, priorité éventuelle |
| PATCH | `/api/v1/sources/{uuid}` | Un champ parmi `name`, `description`, `category`, `priority` + `reason` |
| POST | `/api/v1/sources/{uuid}/deactivate` | `{ "reason": "Justification documentée" }` |
| POST | `/api/v1/sources/{uuid}/activate` | Même corps ; **ne lance aucune collecte** |
| POST | `/api/v1/sources/{uuid}/revoke` | Même corps ; retire l'approbation |
| POST | `/api/v1/sources/{uuid}/approve` | `authorization_confirmed:true`, `authorization_note` |
| DELETE | `/api/v1/sources/{uuid}` | `{ "reason": "Justification documentée" }` ; suppression logique |
| POST | `/api/v1/sources/{uuid}/restore` | `{ "reason": "Justification documentée" }` ; impose `is_active=false`, `approved_for_collection=false` |
| GET | `/api/v1/sources/{uuid}/history` | `limit`, `offset`; historique accessible après suppression |
| POST | `/api/v1/sources/import` | `{ "items": [ { ...mêmes champs qu'une création... } ] }`, max 100 |
| GET | `/api/v1/sources/export.csv` | CSV max 500 ; export non exhaustif au-delà |

Exemple de consultation, sans publier sa clé :

```bash
# Depuis le dossier contenant votre .env ; ne pas afficher la valeur de la clé.
OIP_API_KEY="$(sed -n 's/^OIP_API_KEY=//p' .env)"
curl -fsS -H "X-API-Key: $OIP_API_KEY" 'http://127.0.0.1:8000/api/v1/sources?approved=true&limit=10'
unset OIP_API_KEY
```

Les `POST` de décision exigent un motif explicite (10 caractères au minimum après suppression des espaces). Toute modification d'URL requiert une nouvelle source : on ne change pas silencieusement de domaine approuvé. La description d'une autorisation reste enregistrée dans `onion_sources.authorization_note` et ne figure ni dans les réponses génériques, ni dans les exports CSV.

## Migration et réversibilité

`0002_source_lifecycle` ajoute `is_active` (valeur initiale `true`), `priority` (3), `deleted_at` (`NULL`), l'index `(is_active, deleted_at)` et `audit_logs.details` (`{}`). Les enregistrements préexistants restent présents ; les drapeaux d'approbation préexistants sont conservés. **Cette migration ne lance aucun accès réseau.**

Une rétrogradation Alembic est techniquement possible, mais **elle supprime définitivement les informations ajoutées** (`priority`, `deleted_at`, `details`, etc.). N'exécutez pas `alembic downgrade` sur une base contenant des données utiles sans sauvegarde et plan de retour arrière.

## Tests et limites

- Suite locale de **78 tests passés** sur SQLite sous Python 3.13 avec API FastAPI/SQLAlchemy (y compris mise à niveau d'une base lot 0 contenant une source).
- `docker compose --profile test run --build --rm tests` **à rejouer sur le poste opérateur** (Docker indisponible dans l'environnement de livraison).
- La migration PostgreSQL réelle doit être vérifiée après reconstruction des conteneurs.
- Les pages, connecteurs Tor, rôles utilisateurs, identité nominative et ségrégation des permissions ne sont **pas** implémentés dans cette livraison.
- Une clé API unique protège toutes les opérations ; RBAC et audit nominatif sont reportés au prochain sous-lot de gouvernance, avant déploiement multi-utilisateur.
- Les événements contiennent des motifs libres : ne pas inclure de mots de passe, données personnelles, secrets ou éléments illégaux dans ces motifs.
- L'import est un **import JSON**, pas une lecture de CSV ; l'export CSV est borné et n'est pas un dump complet au-delà de 500 sources.

## Prochaine étape

Terminer l'authentification individuelle et le RBAC avec séparation lecture/écriture, audit d'identité, puis valider le confinement réseau avant l'intégration de Tor.
