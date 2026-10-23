# Préparation GitHub — vérification avant le premier push

*OIP v1.0.0-rc2 · Nettoyage documentaire sans changement fonctionnel*

## Ce qui a été retiré de la publication active

Les notes de lots `docs/00-*` à `docs/17-*`, le schéma SQL d'aperçu (`bootstrap-postgresql-preview.sql`), le README frontend obsolète et le validateur historique `validate-lot8.sh` sont remplacés par une documentation cohérente et les scripts courants.

**Ne supprimez pas** `backend/README.md` (requis par la construction Python), les tests `backend/tests/test_*_lot*.py`, les migrations Alembic 0001–0008, le code Tor, `compose.yaml`, les scripts de sauvegarde/restauration ni `frontend/tests` : ils font partie de la distribution maintenable. **Versionnez** `frontend/package-lock.json`, généré sur votre machine et absent de l'archive RC2 historique.

## Procédure sûre

```bash
cd ~/onion-intelligence-platform
git status --short                           # inspecter les modifications existantes
python3 scripts/cleanup-legacy-docs.py      # simulation, ne modifie rien
python3 scripts/cleanup-legacy-docs.py --apply  # uniquement les anciens fichiers reconnus sans changement

git add README.md docs/ .gitignore .dockerignore .gitattributes scripts/
git add frontend/package-lock.json          # indispensable pour une release reproductible
python3 scripts/pre-push-audit.py           # audit des fichiers suivis + historique
sudo bash scripts/validate-v1.sh --release

git diff --cached --stat
git diff --cached --check
git status --short
```

`cleanup-legacy-docs.py` **refuse** de supprimer un fichier historique s'il diffère de l'archive RC2 de référence. Les opérations sont limitées à une liste explicite, ne touchent pas aux fichiers inconnus ni aux données privées. Si une ancienne note a été modifiée, traitez-la manuellement avant de réexécuter `--apply` ; ne l'écrasez pas.

Le manifeste SHA-256 fourni vérifie uniquement les fichiers de **la distribution livrée** et non vos données locales ni le lockfile npm généré sur votre machine. Un succès du manifeste ne prouve **pas** la propreté de l'index Git. Le contrôle `pre-push-audit.py` inspecte l'index et l'historique, y compris les blobs suspectés d'héberger des secrets. Les sorties ne contiennent pas les valeurs détectées.

## Fichiers à proscrire absolument

`.env` et variantes locales, `backups/`, archives `*.zip`/`*.dump`, bases `*.db`/`*.sqlite`, `node_modules/`, `dist/`, environnements Python, traces Playwright, rapports HTML, journaux `*.log`, captures, clés privées, fichiers de jetons, résultats et exports réels de collecte Onion, et les fichiers de conversations/transcriptions ou logs de terminal contenant des secrets.

**Attention :** `.gitignore` empêche de nouveaux suivis ; il ne retire **ni** un fichier déjà indexé **ni** une donnée déjà présente dans l'historique. Le nettoyage des docs dans le dernier commit ne suffit pas à effacer un secret d'un ancien commit.

## Contrôles d'historique et fuite de secrets

1. Exécutez `python3 scripts/pre-push-audit.py` dans votre vrai dépôt, pas dans un simple ZIP. Le script analyse les fichiers **indexés** et parcourt les objets de commits locaux ; la sortie affiche seulement les chemins/références suspectes.
2. Si une valeur secrète a été commitée dans le passé, **bloquez le push**. Faites d'abord la rotation/révocation du secret. Puis purge du dépôt avec un outil de réécriture d'historique adapté (`git filter-repo`, en clone de travail après sauvegarde et validation). N'effacez pas à l'aveugle les tags ou le dépôt existant.
3. Si un dépôt distant existe déjà, la réécriture exige une coordination avec ses utilisateurs et la suppression des anciennes références/snapshots. Refaire le push ne garantit jamais la disparition d'une fuite.
4. Inspectez aussi les éventuelles branches/tags non fusionnés. Un simple `git status` propre ne prouve pas l'absence de fichiers indésirables dans les commits précédents.

Les identifiants historiques partagés hors Git (clé API, mot de passe PostgreSQL de démonstration) doivent aussi être **renouvelés** avant la mise en ligne. Reportez-vous au [guide d'administration](installation-administration.md).

## Contrôle final avant publication

- [ ] Vérification des modifications et suppressions prévues dans `git diff --cached --stat`.
- [ ] Aucun secret ni donnée réelle dans les fichiers suivis ou dans **aucun commit accessible**.
- [ ] `frontend/package-lock.json` suivi par Git et conforme à `package.json` (`npm ci`).
- [ ] Audits en ligne réussis au moment de la publication ; tests backend, TypeScript et Chromium confirmés.
- [ ] `.env` local renouvelé, mot de passe PostgreSQL réel et jetons sensibles révoqués si nécessaire.
- [ ] Exposition de Nginx conservée à `127.0.0.1`, Tor/worker/DB sans ports publiés.
- [ ] Absence de captures, backups, logs et données Onion dans la distribution publique.
- [ ] **Licence** décidée par le titulaire des droits et ajoutée seulement avec son autorisation. À défaut, indiquer clairement qu'aucune licence de réutilisation n'est accordée.
- [ ] Tag de référence `v1.0.0-rc2` conservé, puis commit de polissage distinct ; **pas de `v1.0.0` stable** avant recette fonctionnelle et rotation des secrets.

## Ce que l'audit automatique ne prouve pas

Il ne détecte pas tous les secrets imaginables, les données sensibles sémantiquement (textes « innocents » mais privés), les blobs Git LFS hébergés ailleurs, les copies sur des forks, ni l'historique distant inaccessible. Réalisez toujours une revue humaine avant un dépôt public.
