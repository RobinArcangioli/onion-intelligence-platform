# Vérifications avant un push GitHub

## Ce qui a été retiré de la publication active

Les notes de lots `docs/00-*` à `docs/17-*`, le schéma SQL d'aperçu (`bootstrap-postgresql-preview.sql`), le README frontend obsolète et le validateur historique `validate-lot8.sh` sont remplacés par une documentation cohérente et les scripts courants.

Conservez `backend/README.md`, requis par la construction Python, les tests
des lots, toute la chaîne de migrations Alembic, le code Tor, `compose.yaml`,
les outils de dump local avant migration et de restauration, et
`frontend/tests`. Les verrous Python et npm font partie du dépôt.

## Procédure sûre

```bash
cd ~/onion-intelligence-platform
git status --short --branch
git diff --cached --stat
git diff --cached --check
python3 scripts/verify-manifest.py
python3 scripts/ci-index-audit.py
python3 scripts/pre-push-audit.py --allow-historical-notes
```

Lancez l’audit sur l’index destiné au commit et rejouez-le après le commit local
pour examiner son message. Comparez les commits à publier à des références
distantes actualisées. L’option `--allow-historical-notes` convient au dépôt
public existant après avoir vérifié que les anciennes notes signalées sont
déjà accessibles depuis les branches publiques. Les contrôles de secrets et
de chemins privés restent bloquants.

Le manifeste SHA-256 couvre les fichiers de la distribution, dont le verrou
npm suivi. L’audit d’index examine les fichiers préparés pour le commit.
L’audit avant push parcourt aussi l’historique local, les messages de commit
et les tags annotés. Les sorties masquent les valeurs détectées.

La qualification de livraison sans démarrage de services est décrite dans le
[README](../README.md#repères-techniques). `validate-v1.sh --release` peut
recréer les services Compose et appliquer les migrations via le démarrage
de l’API. Réservez ce script à une instance de recette dédiée.

## Fichiers à proscrire absolument

`.env` et variantes locales, `backups/`, archives `*.zip`/`*.dump`, bases `*.db`/`*.sqlite`, `node_modules/`, `dist/`, environnements Python, traces Playwright, rapports HTML, journaux `*.log`, captures, clés privées, fichiers de jetons, résultats et exports réels de collecte Onion, et les fichiers de conversations/transcriptions ou logs de terminal contenant des secrets.

**Attention :** `.gitignore` empêche de nouveaux suivis ; il ne retire **ni** un fichier déjà indexé **ni** une donnée déjà présente dans l'historique. Le nettoyage des docs dans le dernier commit ne suffit pas à effacer un secret d'un ancien commit.

## Contrôles d'historique et fuite de secrets

1. Exécutez l’audit avant push depuis le dépôt Git. Les résultats indiquent les chemins ou références suspects et la catégorie détectée.
2. Si une valeur secrète a été commitée dans le passé, **bloquez le push**. Faites d'abord la rotation/révocation du secret. Puis purge du dépôt avec un outil de réécriture d'historique adapté (`git filter-repo`, en clone de travail après sauvegarde et validation). N'effacez pas à l'aveugle les tags ou le dépôt existant.
3. Si un dépôt distant existe déjà, la réécriture exige une coordination avec ses utilisateurs et la suppression des anciennes références/snapshots. Refaire le push ne garantit jamais la disparition d'une fuite.
4. Inspectez aussi les éventuelles branches/tags non fusionnés. Un simple `git status` propre ne prouve pas l'absence de fichiers indésirables dans les commits précédents.

Les identifiants historiques partagés hors Git (clé API, mot de passe PostgreSQL de démonstration) doivent aussi être **renouvelés** avant la mise en ligne. Reportez-vous au [guide d'administration](installation-administration.md).

## Contrôle final avant publication

- [ ] Vérification des modifications et suppressions prévues dans `git diff --cached --stat`.
- [ ] Aucun secret ni donnée réelle dans les fichiers suivis ou dans **aucun commit accessible**.
- [ ] `frontend/package-lock.json` suivi par Git et conforme à `package.json` (`npm ci`).
- [ ] Tests backend, TypeScript et Chromium confirmés. Le contrôle de livraison doit passer avant toute promotion. Le propriétaire autorise explicitement chaque push sur la branche de travail.
- [ ] `.env` local renouvelé, mot de passe PostgreSQL réel et jetons sensibles révoqués si nécessaire.
- [ ] Exposition de Nginx conservée à `127.0.0.1`, Tor/worker/DB sans ports publiés.
- [ ] Absence de captures, backups, logs et données Onion dans la distribution publique.
- [ ] Toute décision de licence relève du titulaire des droits et est reportée après le MVP.
- [ ] Tag de référence `v1.0.0-rc2` conservé, puis commit de polissage distinct ; **pas de `v1.0.0` stable** avant recette fonctionnelle et rotation des secrets.

## Ce que l'audit automatique ne prouve pas

Il ne détecte pas tous les secrets imaginables, les données sensibles sémantiquement (textes « innocents » mais privés), les blobs Git LFS hébergés ailleurs, les copies sur des forks, ni l'historique distant inaccessible. Réalisez toujours une revue humaine avant un dépôt public.
