# OIP — Lot 7 / v0.8.0 — Accès nominatifs et consolidation

## Périmètre livré

- Nouveau modèle `operators` / `operator_tokens`, migration `0007_named_access`, sans modification destructive des tables précédentes.
- Authentification par **jeton API personnel**, 256 bits aléatoires, stocké en base **uniquement par empreinte SHA-256**. Aucune authentification par mot de passe, aucun cookie de session et aucun serveur SSO dans ce lot.
- Expiration (1–90 jours), révocation et désactivation immédiates ; le navigateur conserve le jeton **uniquement en mémoire** et l'envoie au même domaine local dans `X-API-Key`.
- Rôles `VIEWER` (lecture), `ANALYST` (lecture, revues CTI, watchlists, alertes, rapports), `ADMIN` (toutes ces opérations et administration des sources, notamment autorisations de collecte).
- Route de consultation de l'identité : `GET /api/v1/auth/me`. Les opérations existantes restent compatibles ; le backend applique les droits indépendamment de l'interface React.
- Audit : les créations et mutations consignent désormais le nom de l'opérateur authentifié, sans jeton ni adresse IP. Les opérations CLI sont consignées sous `local_admin_cli`.
- Isolation Docker conservée : seul `gateway` publie un port et uniquement sur `127.0.0.1:8000` ; le collecteur n'est pas attaché au réseau sortant `tor_egress`.
- Limitation simple du débit API côté Nginx et quotas conteneurs (processus/mémoire collecteur).
- Scripts de sauvegarde et de restauration PostgreSQL au format personnalisé (`pg_dump -Fc` / `pg_restore`). Aucun dump sensible n'est stocké dans le dépôt.

## Mise à niveau sans perte de données

**Important :** sauvegarder avant de modifier le schéma et conserver une copie locale des archives et des secrets.

```bash
cd ~/onion-intelligence-platform
sudo bash scripts/backup-db.sh
# Copier les fichiers depuis le ZIP du lot 7, puis :
sudo docker compose config --quiet
sudo docker compose --profile test run --build --rm tests
sudo docker compose up --build -d
sudo docker compose exec -T api alembic current
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/ready
```

**Révision attendue :** `0007_named_access (head)`.

La variable `OIP_LEGACY_API_KEY_ENABLED` vaut `true` par défaut pour éviter de bloquer un déploiement existant. **C'est une compatibilité de transition, pas un mode de sécurité définitif.** La clé `OIP_API_KEY` reste nécessaire à la configuration existante.

## Remplacer la clé partagée par une clé nominative

Créez un premier opérateur administrateur (le jeton n'apparaît qu'une seule fois à l'écran) :

```bash
sudo docker compose exec -T api python -m app.security.manage_users create operator --role ADMIN --days 30
```

Conservez secrètement la valeur `API_TOKEN=...` affichée ; ne l'insérez jamais dans une commande copiée dans l'historique du shell, un ticket ou Git. Connectez-vous au dashboard avec ce jeton, et confirmez son identité via l'interface ou :

```bash
read -rsp 'OIP token: ' OIP_KEY; echo
curl -fsS -H "X-API-Key: $OIP_KEY" http://127.0.0.1:8000/api/v1/auth/me
unset OIP_KEY
```

**Après validation de ce compte admin**, ajoutez à `.env` (ou modifiez la valeur existante) :

```dotenv
OIP_LEGACY_API_KEY_ENABLED=false
```

Puis redémarrez les services concernés pour activer la coupure :

```bash
sudo docker compose up -d --force-recreate api gateway
```

Le jeton historique de `.env` est alors rejeté par les routes protégées. Vérifiez les réponses HTTP 401 pour l'ancienne clé et 200 pour le nouveau jeton admin. Une erreur de configuration peut encore être réparée depuis l'administration locale de la machine ; ne supprimez pas les fichiers de secrets/volumes sans sauvegarde.

## Opérateurs et révocation

```bash
# Créer des jetons individuels :
sudo docker compose exec -T api python -m app.security.manage_users create reviewer --role ANALYST --days 30
sudo docker compose exec -T api python -m app.security.manage_users create reader --role VIEWER --days 30
# Réémettre un jeton à un utilisateur existant :
sudo docker compose exec -T api python -m app.security.manage_users issue reviewer --days 30
# Liste des utilisateurs et IDs des jetons (aucun secret) :
sudo docker compose exec -T api python -m app.security.manage_users list
# Révoquer un jeton spécifique par identifiant :
sudo docker compose exec -T api python -m app.security.manage_users revoke TOKEN_UUID
# Désactiver définitivement un utilisateur :
sudo docker compose exec -T api python -m app.security.manage_users disable reader
```

L'opérateur `legacy_operator` n'est pas un compte nominatif ; il n'existe qu'en mode transitoire. Le CLI est accessible seulement aux personnes ayant accès à Docker sur l'hôte ; **un accès administrateur Docker équivaut souvent à un accès total à la machine**.

## Sauvegarde/restauration

```bash
# Backup : archive à accès restreint (umask 077) sous backups/
sudo bash scripts/backup-db.sh
# ou :
sudo bash scripts/backup-db.sh backups/pre-release.dump
```

`backups/` est ignoré par Git ; les données restent sensibles même sans corps HTML : chiffrements et sauvegardes hors ligne recommandés. Les sauvegardes ne comprennent **pas** le fichier `.env` ni le répertoire Tor.

La restauration remplace les tables existantes et nécessite l'arrêt des services applicatifs :

```bash
sudo docker compose stop gateway api
sudo bash scripts/restore-db.sh backups/pre-release.dump --confirm-restore
sudo docker compose up -d api gateway
sudo docker compose exec -T api alembic current
```

Pour une validation de la restauration **sans risque**, restaurer d'abord dans un environnement PostgreSQL isolé, jamais directement sur l'instance de production. La restauration réelle n'a pas pu être testée dans l'environnement de préparation (Docker absent).

## Matrice RBAC

| Routes | VIEWER | ANALYST | ADMIN |
|---|:---:|:---:|:---:|
| GET sources, observations, CTI, watchlists, alertes, rapports | Oui | Oui | Oui |
| Modifier watchlists, revue de découverte/classification/alerte, créer des rapports | Non | Oui | Oui |
| Créer/modifier/supprimer des sources, autoriser/révoquer des collectes | Non | Non | Oui |
| `collector` via CLI Docker | Hors API | Hors API | Administrateur machine |

La permission `ADMIN` d'OIP **ne donne pas** d'accès à Docker et le dashboard **n'exécute pas** de collecte Tor.

## Validation exécutée dans l'environnement de préparation

- `pytest` : 166 tests backend réussis, incluant rôles, expiration, révocation, compatibilité clé historique, migration v0.7.0 -> v0.8.0.
- Frontend : 9 tests utilitaires réussis.
- Alembic : test migration SQLite et génération SQL PostgreSQL réussis.
- Administration CLI : création/liste de jeton validée sur SQLite migrée.
- Nginx : syntaxe testée hors Docker (nom d'hôte backend de test substitué) ; configuration Compose analysée statiquement.
- Scripts : `bash -n` sans erreurs.

**À exécuter sur votre machine** : build Vite/React complet, migration PostgreSQL réelle, tests Docker, émission/révocation de jetons via Docker, sauvegarde et restauration sur base de test, test du navigateur, et vérification du chemin réseau réel du collecteur. Les contrôles statiques réseau ne prouvent pas l'absence totale de fuite dans tous les environnements.

## Limites et risques résiduels

- Jetons personnels sans mot de passe/MFA ; ils jouent le rôle de secrets porteurs. Une fuite permet l'accès jusqu'à expiration ou révocation.
- Pas de sessions serveur, de rotation automatique, de politique multi-tenant, ni de suspension automatisée après erreurs d'authentification ; limitation de débit locale Nginx uniquement.
- Le navigateur ne masque pas toutes les commandes interdites aux rôles faibles ; toute tentative est bloquée côté API par HTTP 403.
- L'API reste disponible **en HTTP local** ; ne publiez pas ce service directement sur un réseau externe. Un futur accès distant nécessite TLS et une passerelle d'authentification appropriée.
- Aucun mécanisme de rétention automatique, suppression réglementaire ou validation juridique n'est garanti par ce lot.
