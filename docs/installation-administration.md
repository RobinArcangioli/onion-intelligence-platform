# Installation et administration

*OIP v1.0.0-rc2 · Environnement local Linux + Docker Compose*

## Préparation et déploiement

Installez Docker Engine, Compose v2, Python 3 (scripts de contrôle) et, pour la validation complète, Node.js/npm et Chromium Playwright. Privilégiez une machine isolée, à jour, avec accès administrateur local maîtrisé.

**Installation neuve :**

```bash
cd ~/onion-intelligence-platform
cp .env.example .env
# Éditer .env localement : remplacer toutes les valeurs d'exemple
# par des valeurs aléatoires distinctes, longues et non réutilisées.
chmod 600 .env
sudo docker compose config --quiet
sudo docker compose up --build -d
sudo docker compose exec -T api alembic current   # 0008_manual_queue (head)
curl -fsS http://127.0.0.1:8000/api/ready
```

**Mise à niveau :** sauvegardez d'abord la base via `sudo bash scripts/backup-db.sh`. Conservez `.env`, les volumes Docker et les jetons existants. L'API applique les migrations Alembic au démarrage. Ne faites jamais `docker compose down -v` pour mettre à jour OIP.

Le dashboard est servi sur **http://127.0.0.1:8000/** ; seul Nginx publie un port hôte. PostgreSQL, FastAPI, Tor et le worker ne publient aucun port. Évitez de changer cette liaison loopback en `0.0.0.0` sans concevoir un déploiement d'accès distinct et sécurisé.

## Comptes et jetons RBAC

Créer le premier opérateur :

```bash
sudo docker compose exec -T api python -m app.security.manage_users create operator --role ADMIN --days 30
```

Créer un autre opérateur, émettre un nouveau jeton ou lister les comptes :

```bash
sudo docker compose exec -T api python -m app.security.manage_users create analyste --role ANALYST --days 30
sudo docker compose exec -T api python -m app.security.manage_users issue operator --days 30
sudo docker compose exec -T api python -m app.security.manage_users list
```

La création et l'émission affichent une valeur `API_TOKEN` **une seule fois**. Ne l'affichez pas dans les logs, shell scripts, captures d'écran, tickets ou commits. Évitez d'enregistrer la sortie du terminal. Pour révoquer un jeton, utilisez **son identifiant UUID** (pas sa valeur secrète) :

```bash
sudo docker compose exec -T api python -m app.security.manage_users revoke UUID_DU_JETON
```

La commande `disable NOM_UTILISATEUR` désactive l'opérateur et ses jetons. Les rôles sont `VIEWER` (lecture), `ANALYST` (collecte autorisée et travail analytique) et `ADMIN` (gestion/approbations). La clé partagée historique doit rester coupée avec `OIP_LEGACY_API_KEY_ENABLED=false`. Vérifiez votre jeton personnel avant toute transition.

## Activer le consommateur des collectes manuelles

```bash
sudo docker compose --profile tor up --build -d tor queue_worker
sudo docker compose logs --tail=30 tor queue_worker
```

Dans les logs Tor, vérifiez que le bootstrap est terminé. Le worker **ne planifie pas** de collecte ; il traite les jobs `PENDING` déposés à la demande par des opérateurs autorisés. La validation du réseau peut être réalisée sans requête Onion :

```bash
sudo bash scripts/check-network-isolation.sh
```

Pour arrêter le traitement : `sudo docker compose stop queue_worker`. Pour traiter les jobs abandonnés par un worker arrêté brutalement, suivez la procédure documentée dans le [guide d'architecture](architecture-securite.md) : ne marquez pas des jobs actifs comme en échec.

## Sauvegarde et restauration

```bash
sudo bash scripts/backup-db.sh                    # dump PostgreSQL dans backups/ (mode 0600)
sudo bash scripts/check-backup-restore.sh          # restauration dans une base temporaire
```

**Les sauvegardes contiennent des métadonnées sensibles.** Chiffrez-les hors dépôt, limitez leur accès, définissez votre rétention et testez périodiquement la restauration. La commande `scripts/restore-db.sh ... --confirm-restore` remplace des données : elle n'est pas utilisée par les validations automatiques. Planifiez un arrêt complet des composants applicatifs et une sauvegarde indépendante avant toute restauration réelle, sur copie validée si possible.

## Rotation des identifiants avant publication

Une valeur de clé API historique a été partagée hors du dépôt lors des tests. Renouvelez-la **même si son authentification est désactivée**. Le mot de passe PostgreSQL observé dans les exemples opérateur ressemblait à un placeholder ; vérifiez qu'un véritable secret est utilisé.

Pour une **base PostgreSQL déjà initialisée**, modifier `OIP_DB_PASSWORD` dans `.env` ne suffit **pas** : l'utilisateur interne conserve son ancien mot de passe. Effectuez une courte maintenance : sauvegarde vérifiée, arrêt des services consommateurs, session `psql` interactive sous compte autorisé, commande `\password oip` (ou votre utilisateur réellement configuré), mise à jour **locale et secrète** de `.env`, puis recréation des services qui consomment les identifiants et vérification de la connexion. Ne mettez jamais le nouveau mot de passe sur la ligne de commande ou dans Git. Ne changez pas un mot de passe inconnu sans un accès administrateur de récupération.

Si votre `.env` contient une ancienne `OIP_API_KEY`, remplacez-la localement par une valeur aléatoire distincte ; recréez l'API et gardez `OIP_LEGACY_API_KEY_ENABLED=false`. Les jetons nominatifs sont indépendants de cette clé. Si un jeton nominatif a lui aussi été exposé, révoquez-le puis réémettez-en un.

## Validation et dépannage

```bash
sudo bash scripts/validate-v1.sh --core
sudo bash scripts/validate-v1.sh --release
sudo docker compose ps
sudo docker compose logs --tail=50 api gateway
sudo docker compose --profile tor logs --tail=50 tor queue_worker
```

La validation `--release` utilise les registres publics npm et PyPI pour l'audit des dépendances et requiert `frontend/package-lock.json` et les navigateurs Playwright. Elle ne visite pas de source Onion. Générer et versionner le lockfile si absent :

```bash
(cd frontend && npm install --package-lock-only --ignore-scripts --no-fund)
```

Ne copiez **jamais** la sortie complète de `docker compose config --format json` dans un rapport : elle peut inclure des variables d'environnement contenant des secrets. Utilisez `docker compose config --quiet` pour un contrôle humain.

| Problème | Diagnostic |
|---|---|
| `PENDING` persistant | `queue_worker` non démarré ou inaccessible ; vérifier les logs du worker. |
| Tor ne termine pas son bootstrap | Vérifier la connexion Tor, l'heure de la machine et les logs ; ne pas désactiver les protections réseau. |
| Le dashboard refuse le jeton | Expiration, révocation, identité inactive ou mauvais rôle ; renouveler le jeton personnel. |
| API `503` | Vérifier la santé de PostgreSQL et la migration Alembic. |
| Playwright manque de navigateur | Installer Chromium pour le compte de l'utilisateur : `npx playwright install chromium`. |

Pour préparer un dépôt GitHub propre, consultez [Publication GitHub](publication-github.md).
