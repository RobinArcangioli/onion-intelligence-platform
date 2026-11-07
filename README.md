# Onion Intelligence Platform (OIP)

Veille documentaire contrôlée sur des sources `.onion` v3 explicitement autorisées.
Base reprise : **M7-C1.1**, commit `44101c593d19f0ee8122bf3d7d10607fde541a12`.
Versions des paquets : `1.0.0rc2` (backend) et `1.0.0-rc.2` (frontend).

## Les deux références du projet

1. **[État de référence](docs/ETAT_DE_REFERENCE.md)** : code existant, architecture,
   capacités et limites, provenance, validations CI/locales, dernier état OVH
   attesté et inconnues.
2. **[Roadmap et décisions](docs/ROADMAP_ET_DECISIONS.md)** : décisions du propriétaire,
   étapes prioritaires, dépendances et critères de sortie.

Ces documents centralisent le statut du projet. Les guides de lots restent des
références techniques de détail ; leurs statuts opérationnels décrivent leur époque.
La [passation](HANDOFF_CODEX.md) et les [preuves de provenance](docs/handoff/PROVENANCE_AND_AUDIT.md)
expliquent la base importée. Aucun accès OVH n'est autorisé par ces documents.

## Cible MVP retenue le 5 novembre 2026

Collecte **manuelle permanente et supervisée**, scheduler désactivé. Un
**administrateur conserve la connexion actuelle par jeton API individuel** ; une **vitrine visiteur** permet
aux clients de consulter certaines informations sur les dernières veilles, sans
accès aux fonctions ni aux informations sensibles. Le jeton API individuel reste la seule méthode d’authentification ; aucun
mot de passe distinct ni écran de gestion de mot de passe n’est à développer.
La connexion et les rôles actuels sont conservés. La seule sauvegarde prévue est le dump local avant migration.

À la même adresse web, un petit lien **« accès visiteur »** ouvre la vue restreinte
sans connexion. Les dernières veilles affichent publiquement **date, statut,
volumes et noms des sources, sans adresse Onion**. L’admin peut également publier
explicitement certains rapports ; les autres informations restent internes.
Ces décisions sont implémentées sur `feature/mvp-visitor-public-boundary` :
API publiques séparées, aperçu/publication/retrait réservés à ADMIN et versions
publiques limitées à la période et aux compteurs. La migration additive `0018`
est validée sur PostgreSQL 17 par les quatre jobs verts du
[run 42025061147](https://github.com/RobinArcangioli/onion-intelligence-platform/actions/runs/42025061147),
commit applicatif `e75d678`. Elle n’est pas appliquée à OVH.

L’adresse locale OIP est [127.0.0.1:8000](http://127.0.0.1:8000). Pour tester
sans données réelles après le build frontend, libérer ce port en arrêtant la
passerelle locale, puis lancer `.venv/bin/python scripts/serve-visitor-demo.py`.
Ouvrir la même adresse et cliquer **Accès visiteur**.
Ce serveur utilise une base synthétique temporaire et n’accepte pas les jetons
opérationnels. Pour son admin de démonstration uniquement, le jeton de fixture
est `oip_CI_SYNTHETIC_NOT_A_REAL_OPERATOR_CREDENTIAL`. La vitrine synchronise
les publications et permet de les ouvrir via **Consulter le rapport**.

### Simulation complète de deux fuites fictives

Après le build frontend, libérer le port 8000, lancer
`.venv/bin/python scripts/serve-visitor-demo.py --simulation` et ouvrir
[l’adresse locale OIP](http://127.0.0.1:8000). La base temporaire démarre avec
deux sources fictives et aucun rapport. Utiliser le jeton de fixture indiqué ci-dessus.

1. Dans **Rapports**, cliquer sur **Lancer les deux veilles simulées**. Dans **Alertes**,
   vérifier les deux alertes **Fuite de données suspectée** et les acquitter si souhaité.
2. Dans **Rapports**, ouvrir **Vitrine** pour chaque rapport. Relire les champs publics,
   actualiser l’aperçu si un champ a changé, confirmer la revue et cliquer sur
   **Publier le rapport relu**.
3. Dans une fenêtre sans session admin, ouvrir **Accès visiteur**, puis **Rapports publics**
   et **Consulter le rapport**. Le retrait depuis **Vitrine** révoque la lecture publique.

Les deux cas représentent des annonces fictives portant sur 2 500 fiches clients
(ALPHA-01) et 750 dossiers RH (BETA-02). Le worker traite deux réponses HTML locales.
Le visiteur lit uniquement la fiche relue et ses compteurs publics.

### Recette navigateur synthétique

Après installation des dépendances frontend, backend et Chromium Playwright,
lancer `npm --prefix frontend run test:e2e` sous Linux. La commande lance
successivement les jeux visiteur, simulation de fuite et recette multi-URL
sur le port 8000 d’un espace réseau limité à la boucle locale. Le serveur
de test utilise une base jetable, un jeton de fixture et un transport simulé.
L’instance de travail reste accessible à son adresse habituelle.

### Gérer les URL d’une marketplace

Dans **Sources → Gérer les URL**, ajoute ou retire les adresses du groupe.
Le bouton **Collecter** soumet toutes ses URL actives au worker Tor. Une
vérification de navigateur reconnue apparaît comme un échec sur l’URL concernée.
La file conserve une collecte en cours par groupe.
**Gérer les URL** affiche la progression de la dernière veille, l’adresse en
cours et le motif d’échec par URL. Lorsqu’une collecte est temporairement
suspendue, OIP indique la date à partir de laquelle une nouvelle tentative
est possible.

**Visiter l’URL** affiche l’adresse et demande de confirmer son ouverture dans
Tor Browser. Une fois la page atteinte, colle son URL finale dans OIP. Utilise
**Ajouter l’URL** pour l’enregistrer seule ou colle aussi le texte visible et
clique **Ajouter et analyser maintenant**. OIP analyse ce texte en mémoire
et indique **Capture opérateur** dans la provenance de l’observation.
Les adresses acceptées sont des URL Onion v3 HTTP(S) avec un chemin simple.
Les paramètres et fragments sont refusés.

Sur Linux, le bouton d’ouverture utilise le lanceur Tor Browser installé
sur le poste. Pour enregistrer le lien local depuis le dépôt, indiquer le
chemin réel de l’exécutable `start-tor-browser`.

```sh
python3 scripts/open-tor-browser.py --install --browser /chemin/vers/Browser/start-tor-browser
```

Sans lanceur enregistré, copie l’adresse affichée et ouvre-la dans Tor Browser.

### Découverte prioritaire de marketplaces

Avec le worker Tor de la stack locale en cours d’exécution, lancer
`.venv/bin/python scripts/import-torwatch.py` pour sonder les dix premières
fiches de la section Markets dans l’ordre du catalogue. Ajouter `--save` pour
enregistrer le premier miroir admissible par fiche dans **Sources**, sous
`MARKETPLACE` avec la priorité P5. Le test exige une réponse HTTP 200 de type
HTML ou texte via Tor. La collecte reste soumise à l’approbation de l’admin.

Si Tor.watch sert une page de vérification au client HTTP, utiliser
`--catalog chemin.json` avec les dix fiches relevées dans le navigateur. Le
fichier est un tableau d’objets `{path, name, mirrors}` en ordre d’affichage.
`path` est le chemin `/service/…` de la fiche et `mirrors` contient les racines
Onion de sa section **Service URLs**, dans l’ordre affiché. Conserver ce fichier
en dehors du dépôt.

Les découvertes ne sont jamais suivies automatiquement. Les limites de transport,
les autorisations de sources, l'arrêt d'urgence et la minimisation des contenus
restent des contraintes du produit. Un signal CTI ne prouve pas une compromission.

## État des validations

Au commit de référence, la [CI du 5 novembre](https://github.com/RobinArcangioli/onion-intelligence-platform/actions/runs/42012518293)
est historiquement **rouge** : le test Nginx échoue sur la permission de
`/run/nginx.pid`. La correction de stabilisation passe localement les 23 tests
de politique avec Nginx présent. Le commit stabilisé **`244437b`** est validé par
les **quatre jobs verts** du [run 42018926671](https://github.com/RobinArcangioli/onion-intelligence-platform/actions/runs/42018926671).
Backend, frontend et recettes PostgreSQL 17 passent ; portée et chiffres exacts
dans l'état de référence. La recette de concurrence des workers et la qualification
de l'exploitation durable restent à faire. Le [dernier état OVH attesté](docs/handoff/OVH_STATE.md)
est historique, sans contrôle en temps réel.

## Repères techniques

| Chemin | Rôle |
|---|---|
| `backend/app/` | API FastAPI, collecte, planification SQL, CTI, dossiers et contrôles |
| `backend/alembic/versions/` | Migrations indispensables `0001` à `0017` |
| `backend/tests/` | Régressions synthétiques et recettes PostgreSQL isolées |
| `frontend/src/` | Interface React / TypeScript |
| `deploy/ovh/` | Profil privé, prévol, supervision, sauvegarde et restauration |
| `docs/m*.md` | Contrats techniques des lots, statuts historiques balisés |
| `.github/workflows/oip-ci.yml` | Validation sans déploiement automatique |

Ne pas démarrer l'API sur une base existante pour une simple inspection : son
image exécute Alembic au démarrage. Les tests PostgreSQL nécessitent des bases
locales vides dédiées, avec DSN explicitement vérifiés ; aucun secret ni donnée
réelle ne doit être utilisé dans les fixtures.

Contrôles locaux sans activation de collecte :

```bash
python3 scripts/verify-manifest.py
python3 scripts/ci-index-audit.py
python3 -m unittest discover -s deploy/ovh/tests -q
```

Le contrôle d'index lit les octets indexés, pas les modifications non indexées.
Le manifeste racine décrit la copie stabilisée ; le [manifeste M7-C1.1 original](docs/handoff/M7C11_SOURCE_SHA256SUMS.txt)
est conservé séparément et dans le commit de référence.

Pour qualifier les images candidates sans lancer les services, exécuter
les commandes ci-dessous. Les builds téléchargent leurs composants publics.
Le scan télécharge la base d’avis Trivy puis s’exécute hors réseau. Les
rapports sont conservés dans le dossier temporaire affiché.

```bash
reports="$(mktemp -d)"
printf '%s\n' "$reports"
candidate="oip-qualification-${reports##*.}"
bash scripts/build-delivery-images.sh "$candidate"
bash scripts/delivery-inventory.sh "$candidate" > "$reports/inventory.txt"
bash scripts/audit-dependencies.sh "$reports" \
  "$candidate:backend" "$candidate:backend-test" "$candidate:frontend-build" \
  "$candidate:gateway" "$candidate:tor" "$candidate:postgres"
```

Pour actualiser les verrous Python, installer uv 0.13.7 puis lancer
`bash scripts/lock-backend.sh`. Pour modifier les dépendances npm, mettre à
jour le verrou avec la version Node fixée dans la CI et le CLI npm vérifié
par `scripts/install-locked-npm.sh`, puis valider avec `npm ci`.
Mettre à jour ensemble les références PostgreSQL de Compose, de la
CI et du script de recette M7-C. Lors d’un changement d’image Python ou
Node, aligner la version exacte du runtime de CI. Lors d’une mise à jour de
Tor ou des correctifs Debian du backend, vérifier les index signés et les
versions dans les instantanés concernés. Le correctif Alpine de la passerelle
requiert la version exacte de `libexpat` dans le dépôt signé. Refaire deux
builds sans cache et comparer leurs inventaires avant de retenir de nouvelles
références.

Aucune licence open source n'est définie à ce stade. Le propriétaire reporte toute
décision de licence après le MVP ; elle ne fait pas partie de la roadmap active.
