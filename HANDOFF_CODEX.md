# Passation OIP à Codex — M7-C1.1

Date de préparation : 5 novembre 2026 (Europe/Paris).

## Prompt de reprise

Tu reprends **RobinArcangioli/onion-intelligence-platform**, sur la branche
`feature/m7c1-1-codex-handoff-20261105`, issue de `main` au commit
`ff7e469fb6f991ee6f69e76754a65abf64d335f8`. Préserve les commits, les branches,
les tags et les modifications locales des autres copies. Ne recrée pas le dépôt,
ne fais pas de force-push et ne réécris pas l’historique.

Lis d’abord ce fichier, [le dernier état OVH attesté](docs/handoff/OVH_STATE.md),
[la provenance et les validations](docs/handoff/PROVENANCE_AND_AUDIT.md), puis
`docs/m7c-postgresql-authentication.md`, les guides M2 à M7 et `deploy/ovh/`.
Les mentions « hors production » et « non déployé » du README et des anciens
lots décrivent leurs étapes de développement : ne les prends pas pour une
photographie actuelle d’OVH. Les versions des paquets restent `1.0.0rc2` et
`1.0.0-rc.2` ; **M7-C1.1 est le jalon de livraison**, pas une version semver.

Le code de référence vient du paquet M7-C1.1 vérifié, avec les migrations
`0001_bootstrap` à `0017_case_notification_drafts`. Stack : Python 3.12,
FastAPI, SQLAlchemy/Alembic, PostgreSQL 17, React/TypeScript/Vite, Nginx et
Docker Compose. Les incréments incluent la file de collecte avec leases et
garde-fous, la planification gouvernée opt-in, l’exploration et la recherche
d’observations, le triage CTI/IOC, les dossiers analystes, des brouillons de
notification locaux et la gouvernance des identités/jetons. Vérifie chaque
capacité dans le code et les tests ; leur présence ne vaut pas qualification
de production.

**Aucun accès à OVH n’est autorisé par cette passation.** Ne te connecte pas
au VPS, ne déploie rien, ne migre aucune base réelle et n’active ni Tor,
ni worker, ni scheduler. Toute intervention distante demande une instruction
ultérieure explicite de l’utilisateur. Ne lis et n’affiche aucun `.env`, clé,
jeton, dump, export ou contenu réel d’observation. Les secrets et données
opérationnelles restent hors Git. Les seules preuves publiées sont des
synthèses expurgées ; aucun accès serveur n’a eu lieu pour cette livraison.

Le dernier pilote attesté dans la conversation d’origine a terminé un job
avec une observation HTTP 200, 20 788 octets reçus, 117 caractères extraits et
`FIRST_SEEN`. Ensuite, les deux indicateurs de collecte de l’API étaient
`false` et Tor était arrêté. Le moniteur redevient sain quand les services de
collecte sont arrêtés. Ne présente pas ces preuves historiques comme un
contrôle en temps réel, ni comme une démonstration d’anonymat ou d’absence de
fuite réseau. Les sauvegardes automatiques restent reportées.

Commence par une inspection locale : état Git, différences avec `main`,
cohérence du manifeste, migrations, contrôles de sécurité et tests. Exécute
les scénarios sur des données synthétiques uniquement. Les tests PostgreSQL
17 exigent des bases locales vides dédiées ; ne réutilise jamais une base
existante. N’active pas leurs variables DSN par héritage sans les vérifier.

La prochaine piste proposée dans l’ancien échange est une collecte manuelle
permanente et supervisée : Tor interne, un worker, concurrence bornée,
sources autorisées, quotas, arrêt d’urgence et scheduler désactivé. C’est
**un travail à préparer localement**, pas une activation approuvée. Le
moniteur actuel refuse tout service de collecte actif ; son modèle doit être
adapté et testé avant toute future exploitation de ce type. Maintiens
l’absence de navigation automatique vers les découvertes, les limites de
collecte, les contrôles RBAC et la minimisation des contenus.

Ta première livraison : une photographie factuelle du code et des tests
exécutés, les écarts documentaires, un backlog court priorisé, puis un premier
incrément local réversible et testé. Réévalue les contrôles de restauration,
la sécurité réseau et les autorisations avant de proposer une procédure de
déploiement. Ne mélange pas les travaux locaux M7-C2/C3/C4 avec cette base
M7-C1.1 sans comparaison et demande explicite de périmètre.

## Récupérer cette branche

Sur une nouvelle copie :

```bash
git clone --branch feature/m7c1-1-codex-handoff-20261105 --single-branch https://github.com/RobinArcangioli/onion-intelligence-platform.git
cd onion-intelligence-platform
```

Dans une copie existante, commence par `git status` ; préserve tout travail
local avant de changer de branche. Si la branche n’existe pas localement :

```bash
git fetch origin
git switch --track origin/feature/m7c1-1-codex-handoff-20261105
```

Si elle existe déjà :

```bash
git switch feature/m7c1-1-codex-handoff-20261105
git pull --ff-only origin feature/m7c1-1-codex-handoff-20261105
```

Ouvre ensuite `HANDOFF_CODEX.md`. Le téléchargement d’archives, l’accès à
l’ancienne conversation et les fichiers secrets ne sont pas nécessaires à
la reprise du développement local.
