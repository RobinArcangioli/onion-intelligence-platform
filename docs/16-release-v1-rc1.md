# OIP v1.0.0-rc1 — guide de release candidate

**Statut : release candidate, pas encore v1.0.0 stable.**

## Ce qui est livré

- Durcissement du routage des requêtes dans React : rejet des chemins normalisés hors de `/api/` et des encodages suspects avant d'ajouter `X-API-Key`.
- Tests navigateur renforcés : clé non conservée dans `localStorage`/`sessionStorage`, disparition après rechargement ou déconnexion.
- Clé partagée **désactivée par défaut** dans les nouveaux déploiements (`OIP_LEGACY_API_KEY_ENABLED=false`). Sur une installation existante, la valeur explicite du `.env` est préservée.
- Scripts `validate-v1.sh`, `check-release-config.py`, `audit-dependencies.sh` et `verify-manifest.py`.
- Tests backend supplémentaires sur les garde-fous de la release.
- Manifeste SHA-256 des fichiers livrés.

**Aucune nouvelle migration PostgreSQL.** Révision cible : `0007_named_access`.

## Mise à niveau depuis v0.9.0

1. Confirmer le commit/tag Git du lot 8 et sauvegarder la base **avant** d'écraser les fichiers.
2. Confirmer qu'un jeton `ADMIN` nominatif est fonctionnel ; si l'ancienne clé est votre seul accès, **ne la désactivez pas avant** la création du jeton.
3. Extraire le ZIP à la racine du dépôt, puis exécuter les contrôles de base.

```bash
cd ~/onion-intelligence-platform
sudo bash scripts/backup-db.sh
# Commande après téléchargement depuis la conversation :
unzip -o ~/Downloads/OIP_v1.0.0-rc1_release_candidate.zip -d .
sudo bash scripts/validate-v1.sh --core
```

Le contrôle `--core` vérifie : le Compose résolu, 176 tests hors réseau, le démarrage FastAPI/Nginx, la passerelle HTTP locale, le réseau réel du collecteur, et une restauration dans une base temporaire (sans écraser OIP). **Aucun service Onion n'est contacté**.

Le script réalise aussi une vérification SHA-256 des fichiers de la release. Elle échouera si vous modifiez un fichier livré entre-temps ; dans ce cas, revérifiez le diff au lieu de forcer le contrôle.

## Basculer vers les comptes nominatifs

La clé partagée historique conserve ses droits d'administrateur **si** votre `.env` contient encore `OIP_LEGACY_API_KEY_ENABLED=true`.

Créer/tester d'abord un jeton personnel, si ce n'est déjà fait :

```bash
sudo docker compose exec -T api python -m app.security.manage_users list
# Si aucun ADMIN, créer le premier opérateur :
sudo docker compose exec -T api python -m app.security.manage_users create operator --role ADMIN --days 30
```

Le jeton est affiché une seule fois. Le conserver hors Git et hors journaux de terminal partagés. Une fois son utilisation vérifiée dans le dashboard, modifier **la ligne existante** dans `.env` :

```dotenv
OIP_LEGACY_API_KEY_ENABLED=false
```

Puis recréer l'API :

```bash
sudo docker compose up -d --force-recreate api gateway
```

**Ne pas partager les secrets, les captures du dashboard ni la sortie complète de `docker compose config`** : elle peut inclure des variables sensibles.

## Verrouiller les dépendances et réaliser les audits

L'archive v1.0.0-rc1 ne contient **pas** de `frontend/package-lock.json`. Notre environnement de génération ne pouvait pas joindre le registre npm (`EAI_AGAIN`). Il serait incorrect d'inventer un fichier de verrouillage. Le Dockerfile accepte encore `npm install` en absence de verrouillage, afin de rester compatible avec la v0.9.0, mais **le contrôle `--release` exige le lockfile**.

Sur une machine de confiance disposant d'un accès autorisé aux registres :

```bash
cd ~/onion-intelligence-platform/frontend
npm install --package-lock-only --ignore-scripts --no-fund
npm ci --ignore-scripts --no-fund
npx playwright install chromium
cd ..
```

Les audits interrogent **les registres publics npm et PyPI depuis votre machine (hors Tor)**. Ils divulguent à ces services au minimum les noms/versions de bibliothèques et les métadonnées réseau usuelles. **Aucun site Onion, jeton d'API ou contenu OIP n'est interrogé ni envoyé**. Si cette politique réseau n'est pas acceptable, ne lancez pas l'audit avant de définir un miroir interne et de l'adapter.

Le script `scripts/audit-dependencies.sh` exécute `npm audit` (incluant les dépendances de build) et `pip-audit` sur les versions effectivement installées dans le conteneur API. Ce sont des vérifications ponctuelles, pas une garantie d'absence de vulnérabilités.

## Dernier contrôle de release (bloquant)

```bash
sudo bash scripts/validate-v1.sh --release
```

Un jeton nominatif sera demandé de manière interactive, sans écho dans le terminal. Il n'est pas passé dans les arguments des processus. Le script exige :

1. Tous les contrôles `--core`.
2. Clé partagée historique désactivée **en pratique** dans le conteneur API.
3. Jeton nominatif valide et smoke test des routes protégées, sans mutation.
4. Lockfile frontend présent, audits npm et Python sans vulnérabilité >= seuil HIGH ou erreur de récupération.
5. Dépendances Node installées et tests unitaires, typage TypeScript et Playwright/Chromium réussis.

Échec ou `SKIP` d'une étape = **pas de feu vert pour v1.0.0 stable**. Si l'installation npm ou Chromium est absente, les commandes ci-dessus sont nécessaires. Le script n'installe pas Chromium automatiquement.

## Restes à valider avant toute exposition publique

- Revue humaine des droits de chaque compte, revocation des jetons inutiles, rotation des secrets.
- Scan de vulnérabilités des **images Docker** par un scanner alimenté en définitions récentes ; l'audit npm/pip ne remplace pas celui des images OS.
- Restauration sur une **autre machine**, secrets et configuration compris, avec chiffrement et rétention des sauvegardes.
- Tests réseau IPv6/UDP et contrôle pare-feu externes à Compose ; la sonde actuelle couvre les flux TCP IPv4 explicités dans ses logs, pas toutes les voies réseau possibles.
- Gouvernance légale des collectes, minimisation et rétention, supervision humaine, gestion des contenus à risque.
- Evaluation du niveau de protection offert par une interface locale seule ; pas d'exposition sur Internet tant que ces contrôles ne sont pas réalisés.

## Traçabilité

Après validation de la candidate **sur votre installation**, commit conseillé :

```bash
git add -A
git diff --cached --check
git commit -m "chore: prepare OIP 1.0 release candidate"
git tag -a v1.0.0-rc1 -m "OIP v1.0.0 release candidate"
```

Le tag stable `v1.0.0` est réservé au succès de toutes les portes de validation et à la revue manuelle des risques résiduels.
