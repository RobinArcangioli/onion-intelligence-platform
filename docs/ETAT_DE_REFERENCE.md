# OIP — État de référence

Révision documentaire : 2026-11-05, Europe/Paris. Statut : référence de
stabilisation ; décisions MVP actées et correction validée par les quatre jobs CI. Les faits ci-dessous sont séparés
des décisions futures consignées dans [la roadmap](ROADMAP_ET_DECISIONS.md).

## 1. Règle de lecture et périmètre

Ce document centralise **ce qui existe et les preuves disponibles**. La roadmap
centralise **ce qui reste à faire et les arbitrages**. Les guides M2–M7 décrivent
les contrats techniques de leurs lots ; leurs mentions de déploiement et leurs
listes de travaux futurs sont historiques. Ils ne constituent plus le suivi du
projet. Aucun fait d'exploitation historique ne vaut constat en temps réel.

Ordre de référence : décision explicite récente du propriétaire ; code et tests
au commit indiqué pour le comportement ; preuve datée pour une validation ou un
état d'exploitation ; présentes références pour la synthèse ; anciens guides
pour le détail. Une contradiction est à résoudre explicitement, jamais par
supposition. Toute évolution doit mettre à jour ces deux références dans le
même changement que le code concerné.

L'inspection porte sur la reprise M7-C1.1 : elle n'est ni un audit exhaustif de
sécurité, ni une étude comparative des outils CTI du marché, ni une recette de
production. Les archives M7-C2/C3/C4 ne sont pas intégrées.

## 2. Identité exacte de la base historique

| Élément | Référence vérifiée |
|---|---|
| Dépôt | [RobinArcangioli/onion-intelligence-platform](https://github.com/RobinArcangioli/onion-intelligence-platform) |
| Branche | `feature/m7c1-1-codex-handoff-20261105` |
| Commit de provenance inspecté et HEAD au clonage | `44101c593d19f0ee8122bf3d7d10607fde541a12` |
| Référence technique stabilisée | `244437baf6d3c8fe8656b50c17a45e09b07a81f6`, CI verte du 5 novembre ; suivi documentaire ultérieur sans changement applicatif |
| Parent / `origin/main` au clonage | `ff7e469fb6f991ee6f69e76754a65abf64d335f8` |
| Arbre du commit de référence | `e0577bcc003704a946d1b595c960ced23502bc3a` |
| Historique récupéré | 12 commits, neuf tags ; branche de reprise un commit devant `main` |
| Écart à `main` | 160 chemins changés, 9 966 insertions / 155 suppressions |
| Index initial | 243 fichiers, état de travail propre |
| Version backend / frontend | `1.0.0rc2` / `1.0.0-rc.2` |
| Jalon de livraison | M7-C1.1, distinct d'une version semver et du tag RC2 historique |
| Tête Alembic de la base M7-C1.1 | `0017_case_notification_drafts` ; chaîne `0001`–`0017` |

Le commit de reprise importe un paquet complet : les jalons M2–M7 ne sont pas
chacun un commit distinct dans cet historique public. Ne pas inventer une
traçabilité commit par lot. Le tag `v1.0.0-rc2` désigne un état antérieur et
n'identifie pas le contenu M7-C1.1.

La provenance attestée est le paquet M7-C1.1, SHA-256
`0e841e4a54157602c7ab2e03dfa0fffb9d38f7385c8e84009edae9f4b4c2de96`,
240 fichiers dont un manifeste de 239 entrées. Les trois fichiers de passation
s'y ajoutaient. Douze fragments vides de sorties terminal ont déjà été retirés
dans le commit de reprise. Voir [provenance et audit](handoff/PROVENANCE_AND_AUDIT.md).

Le manifeste original est conservé à l'identique dans
[handoff/M7C11_SOURCE_SHA256SUMS.txt](handoff/M7C11_SOURCE_SHA256SUMS.txt) et dans
le commit de référence. Après le nettoyage documentaire, le manifeste racine
est celui des sources de la copie stabilisée ; il ne doit pas être présenté
comme une vérification inchangée du paquet original. Les nouveaux documents
et les guides balisés expliquent les écarts documentaires initiaux. Le présent
incrément visiteur constitue ensuite une modification applicative distincte.

### Cible MVP décidée pendant la reprise

Le propriétaire a précisé le 5 novembre 2026 : **conserver la connexion actuelle
par jeton API individuel comme seule méthode d’authentification**, et ajouter une
vitrine visiteur limitée pour les clients, sans accès aux fonctionnalités ni aux
informations sensibles. L’expression « mot de passe » désignait le jeton existant :
aucun nouveau mot de passe, écran de choix/modification ou session cookie à ajouter.
Cette précision remplace les interprétations de retrait complet de l’authentification
ou de remplacement des jetons par une connexion par mot de passe. La priorité reste
la collecte manuelle permanente supervisée, scheduler désactivé, avec sauvegardes
automatiques comme prérequis d’exploitation durable. Le code conserve son
mécanisme de jetons/RBAC, qui correspond au choix retenu. L’accès visiteur,
la séparation de ses données et la publication publique sont implémentés sur la
branche active et validés en CI, avant toute recette opérateur ou déploiement.
Le visiteur utilise la même adresse web que l’admin, via un petit lien latéral
« accès visiteur », sans connexion. Par défaut, date, statut, volumes et noms
des sources des dernières veilles sont publics, **sans adresse Onion**. L’admin
peut en plus publier explicitement certains rapports ; les autres restent internes.
Ces choix D11–D13 sont actés. Les API de vitrine et la publication sont
implémentées dans l’incrément actif ; le rôle `VIEWER` ne devient pas anonyme.
La décision de licence est reportée après le MVP et exclue de la roadmap.

### Incrément actif — accès visiteur et frontière publique

Branche **`feature/mvp-visitor-public-boundary`**, commit applicatif
**`e75d67863982cc08523e9e066e0c11485e7973d4`**, issue de `cd7c343` (clarification
conservant les jetons), elle-même descendante de la base stabilisée. Cet incrément
implémente MVP-01 et MVP-01V, sans déploiement OVH. La tête Alembic de cette
branche est **`0018_public_report_publications`** ; les preuves M7-C1.1 ci-dessous
restent attachées à leur code `0017` historique.

- L’écran de connexion conserve le jeton individuel et ajoute un lien latéral
  **Accès visiteur**. La vue anonyme est en lecture seule, sans clé, cookie ni
  persistance navigateur. Elle ne réutilise pas les listes internes.
- API publiques GET uniquement sous **`/api/public/v1`** : `/activity`, `/reports`
  et `/reports/{publication_id}`. Réponses définies par listes explicites de champs,
  pagination 1–50, offset 0–10 000, `Cache-Control: no-store`.
- Activité : collectes **COMPLETED/FAILED** de sources actives, non supprimées et
  approuvées ; exclusion des observations en quarantaine. Date de fin, ou date de
  création si elle manque ; nom de source ; statut ; octets reçus et caractères
  extraits pour une réussite, valeurs absentes pour un échec. Aucun identifiant
  interne, adresse, titre, extrait, détail d’erreur ou donnée de bail. Les noms
  contenant une adresse Onion/URL, un email ou un marqueur de secret reconnu sont
  masqués. Ce filtre ne remplace pas une revue des noms, désormais publics.
- Rapports : seules les publications explicites sont visibles. L’admin ouvre
  **Rapports → Vitrine**, examine période et cinq compteurs (observations,
  découvertes, classifications, mentions CTI, alertes), puis publie la projection
  **`PUBLIC_TOTALS_V1`**. Ni lignes détaillées, ni identifiants source/observation,
  notes, IOC, texte, noms d’opérateurs ou données d’audit ne sont copiés.
- Publication : version publique à identifiant distinct, contenu figé et empreinte
  d’aperçu vérifiée avant écriture. Verrou sur le rapport et index unique partiel
  empêchent deux versions publiques actives. Dépublication ADMIN : l’URL/API
  devient 404 et la version disparaît de la liste ; une nouvelle publication
  reçoit un nouvel identifiant. Les rapports internes restent intacts et privés.
- Les routes internes **`/api/v1` restent toutes authentifiées** ; publication,
  aperçu et retrait exigent ADMIN. Les rôles/jetons et leur gouvernance restent
  inchangés. Le moniteur continue d’exiger le refus anonyme des sources internes.

La migration `0018` ajoute une table dédiée ; aucun ancien rapport n’est publié
implicitement. Sa rétrogradation supprime les versions publiques : uniquement
sur base jetable, jamais comme stratégie de récupération. Le démarrage d’une
image API avec ce code lancerait cette migration ; aucune mise à jour OVH n’est
réalisée ou autorisée par la livraison du code seul.

**Validation locale de l’incrément :** backend **362 réussites / six skips PG**
sans DSN hérité ; tests ciblés de fuite, refus de rôle, publication/retrait et
migration SQLite jetable ; frontend quatre fichiers de tests unitaires réussis
sur Node 18 et build TypeScript/Vite réussi ; **trois scénarios Playwright réels**
sur serveur local synthétique ; **23 politiques OVH réussies**, Nginx présent.
Les contrôles d’inventaire RBAC ont été renforcés pour parcourir les contextes de
routes effectifs de FastAPI, avec garde contre une liste vide : l’ancienne
introspection pouvait passer sans examiner les routes sur la version installée.
Le job frontend inclut désormais ces trois scénarios navigateur, sur Ubuntu 24.04
pris en charge par les dépendances Playwright installées. Le manifeste courant
couvre **263 fichiers sources**, avec **264 chemins** à l’index (manifeste inclus).
**CI inspectée et verte :** [run 42025061147, tentative 1](https://github.com/RobinArcangioli/onion-intelligence-platform/actions/runs/42025061147),
commit applicatif `e75d67863982cc08523e9e066e0c11485e7973d4`, 5 novembre 2026,
12:11:37–12:12:54 UTC (13:11:37–13:12:54 à Paris). Quatre jobs **SUCCESS** :

| Job | Résultat inspecté |
|---|---|
| Backend et politiques | **362 passed / six skips PG** ; **23 politiques réussies**, zéro skip Nginx ; audit index, syntaxe shell et compile Python réussis |
| Frontend Node 24 / Ubuntu 24.04 | **17 tests unitaires réussis**, zéro skip ; TypeScript/Vite réussis ; **trois scénarios Playwright réussis** |
| PostgreSQL M4-B | **Un test réel réussi**, zéro skip |
| PostgreSQL M7-C | **17 tests réussis**, zéro skip : cinq tests PG réels et douze cas de sécurité/lanceur, dont l’unicité de publication sous deux sessions concurrentes |

Les migrations complètes, le retrait/retour de `0018`, et les protections de
concurrence existantes sont donc également vérifiés sur PG17. Les six skips du
job backend correspondent aux six tests PG couverts dans les deux jobs dédiés.
Ce résultat ne vaut ni test de charge, ni recette réseau cible, ni restauration
hors site. Aucun déploiement OVH. Le suivi documentaire de ces preuves est un
commit ultérieur sans modification applicative.

**Correction après recette utilisateur :** la liste initiale préchargeait les
publications à l’entrée dans la vitrine et ne les relisait pas lors du changement
d’onglet ou d’une publication depuis une autre fenêtre. La vue relit désormais
les données à l’ouverture de l’onglet, au retour sur la fenêtre et toutes les cinq
secondes lorsqu’elle est visible. Un bouton **Consulter le rapport** ouvre la
version publique par son API dédiée ; le lecteur relit son état de publication.
Après retrait par l’admin, le contenu disparaît du lecteur au prochain contrôle
et l’accès public renvoie 404. Le contrat de contenu reste `PUBLIC_TOTALS_V1` :
aucune ligne interne supplémentaire n’est exposée.

La recette navigateur comporte désormais **quatre scénarios**, dont un avec deux
fenêtres indépendantes : publication admin → apparition dans une vitrine déjà
ouverte → consultation → dépublication → contenu inaccessible. Quatre scénarios
réussis localement, build TypeScript/Vite réussi. Le serveur automatique utilise
le port **8011**, distinct de la démonstration manuelle **8010**, pour ne pas
réinitialiser les données de test de l’utilisateur. Les nouvelles captures de
réponse ne contiennent aucune clé opérateur et ne contactent que les API publiques.

Recette manuelle **synthétique** reproductible, après build frontend et installation
des dépendances backend : `.venv/bin/python scripts/serve-visitor-demo.py`, adresse
`http://127.0.0.1:8010`. Le script refuse tout héritage `OIP_*`, utilise une base
SQLite temporaire distincte et une identité de fixture fixe, jamais un jeton réel.
Il ne contacte pas OVH ni Tor. Le tunnel `127.0.0.1:8001` reste distinct et montre
la version réellement déployée, sans cet incrément.

### Simulation locale de bout en bout et rapports relus

Le mode `--simulation` du serveur de démonstration exécute deux demandes de collecte
via l’API authentifiée. Le worker extrait les observations et déclenche deux alertes
`DATA_LEAK_CLAIM` au statut `OBSERVED_CLAIM`, puis l’API crée deux rapports privés,
chacun rattaché à sa source. La réponse du transport est fournie par deux fixtures
HTML en mémoire. Les actions de démonstration sont propres à ce serveur local, avec
une base SQLite jetable.

Le format `PUBLIC_REVIEW_V2` contient la fiche relue par l’admin et les compteurs
publics. La fiche permet de publier le nom de l’entreprise, le secteur, la date de
détection, une synthèse, les catégories de données, le volume annoncé et les
recommandations. Les deux fiches portent une mention de simulation. La confirmation
admin porte sur une empreinte de l’aperçu complet. La version publiée reste figée
jusqu’au retrait. Les réponses publiques s’appuient sur un schéma explicite, distinct
des observations et des alertes internes. Les publications `PUBLIC_TOTALS_V1` restent
lisibles. La tête Alembic reste `0018`.

La [recette manuelle](../README.md#simulation-complète-de-deux-fuites-fictives)
utilisait le port 8012 avant la consolidation sur le port 8000. La recette
Playwright utilise le port 8013 le temps de son exécution.
Validations locales : 5 scénarios Playwright réussis, build TypeScript/Vite réussi,
373 tests backend réussis et 6 tests PostgreSQL ignorés dans cette exécution.

### Accès local unique et découverte Tor.watch

L’interface OIP locale utilise `127.0.0.1:8000`. Les anciennes instances de
démonstration et tunnels locaux sur les ports 8001 et 8010 à 8013 sont fermés
hors tests. Pour démarrer le serveur de démonstration, libérer la même adresse
en arrêtant la passerelle de la stack locale.

L’outil opérateur `scripts/import-torwatch.py` lit les dix premières fiches
**Markets**, puis les miroirs de leur bloc **Service URLs**. Le premier miroir
par fiche répondant en HTTP 200 HTML ou texte via le proxy Tor est candidat.
La sonde lit le statut et les en-têtes. L’option `--save` inscrit les nouvelles
sources en catégorie `MARKETPLACE`, priorité P5, avec provenance dans l’audit.
La collecte et la planification restent désactivées pour ces candidats tant
qu’un admin n’a pas approuvé la source et activé l’usage souhaité.

Première passe réelle locale : dix fiches lues dans le navigateur, après
réponse de vérification du site au client HTTP. Trois fiches ont fourni un
miroir admissible. Cannaexpress et Eden ont été ajoutées à la base locale et
Black Ops était déjà enregistrée. Sept fiches restent sans miroir admissible
sur cette passe. Les validations ciblées de l’import et du transport passent
(28 tests). La recette avec collecte réelle et rapport est une étape distincte.

### Registre d’URL et analyse de la page atteinte dans Tor

La migration `0019_source_pages` place les adresses existantes dans la liste
de leur groupe. Une veille déclenchée sur un groupe prend en charge ses URL
actives et conserve une collecte en cours à la fois pour ce groupe.
Une URL retirée quitte la liste active et son historique reste consultable.

L’admin peut ajouter une URL seule ou analyser immédiatement le texte visible
qu’il colle depuis Tor Browser. L’analyse partage les règles, les alertes et
les rapports du collecteur, conserve la provenance opérateur et traite le
texte en mémoire. La vitrine peut afficher les compteurs d’un rapport publié
selon la procédure habituelle. Les paramètres et fragments d’URL sont refusés.

La recette synthétique vérifie l’ajout seul, l’analyse immédiate, la veille
sur trois URL, le signalement d’une page de vérification et la publication
des compteurs. Le propriétaire a confirmé le parcours opérateur le
7 novembre 2026 sur l’instance locale. Il a collé l’URL et le texte visible,
obtenu une alerte, puis publié un rapport qu’il a consulté en mode visiteur.
Cette confirmation couvre l’analyse manuelle et la publication. La collecte
ordinaire sur une page réelle et l’ouverture via le lanceur Tor restent à
vérifier séparément.

### Qualification PostgreSQL de la file multi-URL

La migration `0020_collection_batches` associe les jobs soumis lors d’une
même veille. L’écran **Gérer les URL** affiche les compteurs, l’URL en cours,
les erreurs par adresse et l’échéance de reprise donnée par le serveur.
Une capture opérateur reste distincte de la progression d’une veille.

La recette sur PostgreSQL 17 jetable a exécuté 19 tests, sans port hôte
supplémentaire. Deux sessions concurrentes ont soumis la même veille et
deux workers ont tenté de la prendre. Trois URL distinctes ont été traitées
une fois chacune malgré un échec intermédiaire. Après expiration et
réconciliation d’un bail, l’URL suivante a repris et le résultat tardif
n’a produit aucune observation.

Le dump synthétique a été chiffré avec `age` et restauré dans une base
PostgreSQL 17 vierge. Les comptes des URL, jobs de veille, observations et
publications sont identiques avant et après la restauration. Cet essai est historique. La politique actuelle limite les dumps à la
sauvegarde locale précédant une migration.

### Supervision locale du worker

Les profils privé et manuel ont passé le prévol Compose avec des paramètres
de recette. Le profil manuel contrôle le worker, le proxy SOCKS local, les
baux expirés et les jobs éligibles qui restent en attente. Le contrôle SOCKS
ne comporte aucune destination. Les erreurs d’un site restent dans les
résultats de la veille.

Sur l’instance locale, la sonde a signalé l’arrêt du worker, puis a validé
son retour ainsi que l’API, l’authentification et le proxy Tor local.
Elle a aussi détecté le dépassement du seuil disque de 85 % pendant
la recette. Les unités systemd journalisent localement. La recette n’a
pas activé le timer ni utilisé une destination distante.

Les outils de transfert de sauvegarde et les unités correspondantes ont
été retirés. Les outils restants couvrent le dump local avant migration
et la vérification d’une archive locale existante.

## 3. Architecture présente

Python 3.12, FastAPI, SQLAlchemy/Alembic, PostgreSQL 17 ; interface React 19 /
TypeScript / Vite ; passerelle Nginx et Docker Compose. L'API écrit les demandes
en base ; un worker distinct réalise le traitement. Le scheduler est un service
SQL séparé, opt-in sous le profil `scheduled`. Il ne transporte aucune requête
Onion lui-même.

Le profil OVH privé impose `db/api/gateway`, une seule publication hôte
`127.0.0.1:8000`, accès opérateur par tunnel SSH, clé legacy désactivée et verrous
API de collecte à `false`. `tor`, `collector` et `queue_worker` sont sous profil
`tor`. Le réseau du worker est limité à `private` et `tor_proxy`, internes ; Tor
possède une sortie dédiée. Ce sont des propriétés de configuration et des
contrôles ciblés, pas une preuve absolue d'absence de fuite.

Attention : le Compose générique et le profil OVH privé n'ont pas les mêmes
valeurs par défaut. `Settings.manual_collection_enabled` vaut `True` dans le
code ; l'overlay OVH force explicitement `false`. Ne pas présenter toute la
pile générique comme fermée par défaut pour les admissions manuelles.

Le démarrage du conteneur API exécute `alembic upgrade head` avant Uvicorn
([Dockerfile](../backend/Dockerfile)). Un changement d'image suivi d'un redémarrage
peut donc migrer une base. Un rollback applicatif n'est pas un rollback de données.

## 4. Inventaire des capacités et limites

« Présent » signifie repéré dans les implémentations et les tests correspondants.
La suite backend de CI est globale ; elle ne qualifie pas chaque capacité sous
charge réelle ou sur un serveur réel.

| Domaine / jalon | Présent dans le code | Limites à conserver |
|---|---|---|
| Registre / RC2 | Sources Onion v3, approbation, cycle de vie, collecte par clic, découvertes examinables | Aucun suivi automatique d'une découverte ; validation syntaxique ≠ autorisation de la source |
| Transport / lot 2 | Racine seule, HTTP 200, SOCKS obligatoire, `trust_env=False`, pas de redirection, MIME textuel, 256 Kio maximum | Ni navigateur JS ni sous-ressources ; réseau cible non requalifié pendant la reprise |
| File / M2-A/B | Timeout réseau global 120 s, bail 180 s, heartbeat 20 s, `SKIP LOCKED`, jeton de bail et contrôle avant conservation | Pas de retry automatique ; récupération administrative après arrêt des workers ; concurrence PG multiworkers restant à démontrer |
| Résilience / M2-C | Cooldown 300 s, max 25 en attente / 2 en cours par défaut, circuit après 3 échecs pour 3 600 s, stop et métriques ADMIN | Sentinelle locale au conteneur ; arrêt coopératif au heartbeat, pas annulation rétroactive d'une requête |
| Planification / M3 | Opt-in ADMIN/source, autorisation expirante, fenêtres UTC, fréquence 60–10 080 min, budget 1–24/jour, audit | Profil et verrous séparés ; aucun scheduler attesté actif ; concurrence multi-instances non couverte par M7-C |
| Observations / M4 | Filtres, pagination, provenance, comparaison de métadonnées et empreintes ; FTS PostgreSQL titre/description, index GIN/B-tree | Pas de recherche ni diff du texte intégral ; `OFFSET` et volumétrie à mesurer |
| Rétention / M4-B | Prévisualisation d'impact ADMIN et compteurs de dépendances | `dry_run=true`, `safe_to_purge=false` ; aucune purge ni durée de conservation approuvée |
| Analyse / lots 3–5 | Mots clés, classifications heuristiques, signaux CTI, alertes dédupliquées, rapports/snapshots | Une mention, une alerte ou un score ne démontre ni compromission, ni exploitation, ni infraction |
| CVE / M5-A | Revue humaine et provenance de références publiques ; corrélations documentaires | Pas d'enrichissement externe ; acceptation de la mention ≠ validation de la CVE ou de son exploitation |
| IOC / M5-B | Domaines/IP publiques/SHA-256 explicitement étiquetés, extraction opt-in, max 24 candidats/observation, revue analyste | Ni résolution réseau ni export IOC ; valeurs sensibles ; exclusion des observations en catégorie protégée |
| Qualité / M5-C | Rubrique explicable versionnée, fraîcheur, cooccurrences CVE/IOC acceptées sur une même observation, audit expurgé | Heuristique non calibrée ; cooccurrence ≠ corroboration indépendante |
| Dossiers / M6-A/B | Un dossier par alerte, assignation, transitions, priorité, notes structurées bornées, contrôle optimiste de version | Notes en clair en base, filtrage partiel ; lecture commune à ANALYST/ADMIN, aucune confidentialité par dossier |
| Opérations / M6-C | Politiques ADMIN, brouillons locaux `NOT_SENT`, agrégats JSON/CSV minimisés | Aucun canal email/webhook, aucun destinataire ni envoi ; doublons/politiques sous concurrence PG à compléter |
| HTTP / M7-A | Allowlist Host, CSP/no-store/autres en-têtes, docs masquées au gateway, contrôle auth/RBAC des routes | Échec historique de permission PID corrigé et validé en CI de stabilisation ; pas une recette HTTP navigateur complète |
| Identités / M7-B/B2 | Jetons nominatifs expirants/révocables, empreinte SHA-256, rotation atomique, quota cinq actifs, protection dernier ADMIN, inventaire personnel | Secrets porteurs, pas de MFA/OIDC/session cookie ; courses rotation/révocation encore à couvrir en PG |
| Recette / M7-C1.1 | Lanceur jetable local, refus DSN dangereux, migrations complètes et trois courses testées en PG | Quatre tests PG M7-C, pas une qualification de tous les scénarios concurrents |
| Exploitation / M1 | Profil privé, prévol, moniteur, scripts sauvegarde/transfert/restauration, unités systemd opt-in | Le moniteur refuse les services Tor/collecte actifs ; automatisation sauvegardes historiquement reportée |

Les implémentations se trouvent dans `backend/app/{api,collector,scheduler,cti,
observation_history,security}`, les modèles et migrations ; les écrans dans
`frontend/src/components/`. Les tests portent les noms des jalons dans
`backend/tests/test_m*.py` ; politiques d'exploitation dans `deploy/ovh/tests/`.

La minimisation porte sur les corps de pages : HTML et texte extrait complet
restent éphémères. Titres (240 caractères), descriptions (500), longueur et hash
sont conservés ; des valeurs IOC et annotations analystes peuvent aussi l'être.
Ne pas résumer cette architecture par « aucune donnée sensible stockée ».
L'extracteur retire notamment scripts, styles, navigation, formulaires et footer ;
un faible texte extrait pour une réponse volumineuse n'est donc pas une anomalie
établie. Une évaluation synthétique de sa qualité reste utile.

## 5. Preuves de validation au commit de référence

### CI GitHub effectivement consultée le 5 novembre 2026

[Run 42012518293, tentative 1](https://github.com/RobinArcangioli/onion-intelligence-platform/actions/runs/42012518293),
commit exact `44101c5…`, événement `push`, 10:39:25–10:40:37 UTC
(11:39:25–11:40:37 à Paris). Conclusion globale : **FAILURE**.

| Job | Résultat et portée constatés dans les logs |
|---|---|
| [Backend et politiques OVH](https://github.com/RobinArcangioli/onion-intelligence-platform/actions/runs/42012518293/job/127194829360) | Audit index PASS ; backend **340 passed, 5 skipped**, 1 avertissement ; politiques **22 réussites / 1 échec**, aucun skip Nginx ; étape syntaxe shell/compile sautée après échec |
| [Frontend](https://github.com/RobinArcangioli/onion-intelligence-platform/actions/runs/42012518293/job/127194829190) | Node 24 ; `npm ci`, **14 tests réussis, 0 ignoré** répartis dans trois fichiers ; TypeScript et build Vite réussis |
| [PostgreSQL M4-B](https://github.com/RobinArcangioli/onion-intelligence-platform/actions/runs/42012518293/job/127194828832) | PostgreSQL **17.11**, **1 test réussi**, aucun ignoré ; migrations, FTS/index et EXPLAIN, 400 observations synthétiques |
| [PostgreSQL M7-C](https://github.com/RobinArcangioli/onion-intelligence-platform/actions/runs/42012518293/job/127194829265) | PostgreSQL **17.11**, **16 tests réussis**, aucun ignoré : quatre tests intégration et douze cas de sécurité/lanceur |

M7-C applique `0001 → 0017`, revient à `0016` puis remet `0017` avant insertion
synthétique ; vérifie schéma/index, désactivation concurrente des deux derniers
ADMIN, deux émissions à quota quatre et deux écritures d'une version de dossier.
Ces preuves satisfont cette recette précise, auparavant annoncée en attente.
Elles ne couvrent pas la concurrence collecte/scheduler, toutes les courses
identité, les notes/politiques/brouillons, la charge ou une restauration réelle.
Le temps EXPLAIN M4-B (0,042 ms dans ce run) n'est pas un SLO représentatif.

Les cinq skips de la suite backend générale correspondent aux tests PG exécutés
dans les deux jobs séparés. Ne pas annoncer « cinq tests jamais exécutés » ; ne
pas additionner les suites pour prétendre à un nombre de tests uniques, car les
cas de sécurité sont également exécutés dans la suite générale.

**Cause du rouge :** `test_nginx_syntax_when_available` crée une configuration
sans directive `pid` dédiée. Nginx annonce une syntaxe correcte puis échoue à
ouvrir `/run/nginx.pid` avec `Permission denied`. La correction de stabilisation isole
le PID et tous les chemins temporaires de test, avec logs sur stderr, en
utilisateur non privilégié ; le test et ses assertions sont conservés. Ne pas conclure à un défaut
syntaxique de la configuration livrée, ni annoncer la CI verte avant une relance.

Absents de ce workflow : Playwright, scan de dépendances en ligne, Gitleaks de
l'historique, build/recette des images complètes, tests réseau réels et restauration
hors site. Le contrôle d'index n'est pas un audit historique.

### CI de stabilisation — preuve verte

Commit **`244437baf6d3c8fe8656b50c17a45e09b07a81f6`**, publié sur la branche de
travail après autorisation du propriétaire. [Run 42018926671, tentative 1](https://github.com/RobinArcangioli/onion-intelligence-platform/actions/runs/42018926671),
5 novembre 2026, 11:26:06–11:27:04 UTC (12:26:06–12:27:04 à Paris),
conclusion globale **SUCCESS**. Les quatre jobs et leurs logs ont été inspectés :

| Job | Résultat au commit stabilisé |
|---|---|
| Backend et politiques OVH | Audit index PASS ; backend **340 passed, 5 skipped**, un avertissement ; politiques **23/23**, Nginx présent, zéro ignoré ; étape syntaxe de tous les scripts et compile Python effectivement réussie |
| Frontend | **14 tests réussis**, zéro ignoré ; installation verrouillée, TypeScript et build Vite réussis |
| PostgreSQL M4-B | **1 test réussi**, zéro ignoré |
| PostgreSQL M7-C | **16 tests réussis**, zéro ignoré |

Les limites de couverture du run initial restent applicables : les cinq skips
du job backend sont les tests PG couverts par les jobs dédiés ; pas de recette
multiworkers, Playwright, scan de dépendances, réseau cible ou restauration réelle.
La correction ne touche ni aux routes métier, ni aux migrations, ni à la
configuration Nginx applicative. `main` et les tags restent inchangés. Le suivi
documentaire de cette preuve est un commit distinct ; ne pas lui attribuer le
SHA du commit technique ci-dessus.

### Preuves historiques de fabrication

La [passation de provenance](handoff/PROVENANCE_AND_AUDIT.md) atteste : manifeste
239 PASS ; backend 340/5 ignorés ; frontend trois suites annoncées réussies et
build ; politiques OVH 22 réussites / un skip Nginx ; syntaxe shell réussie ;
Gitleaks et audit historique sans détection reconnue dans leur périmètre.
Ce sont des preuves héritées, pas des exécutions renouvelées dans cette reprise.

### Vérifications locales de la reprise

Copie clonée dans le dossier de travail convenu, HEAD exact et index initial
propres. Manifeste original **239 PASS** avant modification. Audit index initial
**243 PASS**. Politiques OVH : **23 exécutés, OK avec un ignoré** car Nginx absent
(22 réussites). Python local 3.12.3, Node 18.19.1 ; dépendances Python backend et
frontend non installées dans cette nouvelle copie. Backend, frontend, Playwright
et PostgreSQL n'y sont donc pas revendiqués comme rejoués. Les résultats CI
ci-dessus sont les preuves d'exécution pour ces suites.

La stabilisation comprend le portail README, les balises historiques, les deux
références centrales et la conservation du manifeste source, ainsi que la
correction du test Nginx et du contrôle de syntaxe CI. Le contrôle shell utilise
désormais une boucle vérifiant chaque script, au lieu de `bash -n` avec un glob
qui ne vérifiait que le premier fichier.
Contrôles de la livraison documentaire initiale : manifeste de stabilisation
**245 entrées PASS** (avant l’incrément visiteur),
**72 liens Markdown locaux vérifiés, aucun cassé**, `git diff --check` PASS,
syntaxe de chaque script shell vérifiée individuellement et syntaxe Python OVH
PASS. Audit de l’arbre candidat via un index temporaire : **246 chemins PASS** ;
audit de l’historique récupéré : **432 blobs inspectés**, aucune détection reconnue
ni chemin interdit. Les anciennes notes sont acceptées selon la stratégie de
conservation déjà décidée, sans exemption de secret. Gitleaks et scans de
dépendances ne sont pas rejoués. Le 5 novembre, après autorisation de poursuivre,
la défaillance originale d’accès à `/run/nginx.pid` a été reproduite avec le vrai
binaire Nginx Ubuntu 1.24.0 extrait sous `/tmp`. La suite corrigée retourne
**23 tests réussis, zéro ignoré**, hors sandbox pour permettre les vérifications
de sockets de `nginx -t`, sans privilège root ni démarrage de service. La
configuration Nginx applicative reste inchangée. La validation distante du commit
de stabilisation est le run vert `42018926671`, distinct du run initial rouge
`42012518293` sur `44101c5…`.

## 6. Dernier état OVH attesté et inconnues

Source : [OVH_STATE.md](handoff/OVH_STATE.md), synthèse du 5 novembre d'éléments
opérateur dont les journaux du pilote portent la date du 25 octobre, fuseau non
établi. **Aucune connexion OVH pendant l’audit initial.** Après instruction explicite
ultérieure du propriétaire, un tunnel SSH en lecture a été ouvert vers l’interface
existante sur le port local 8001 : page OIP, santé et disponibilité HTTP 200,
sources anonymes HTTP 401. Aucun déploiement, migration ou contrôle de données
métier n’a été effectué. Cette vérification ciblée ne requalifie pas l’ensemble
des services, du réseau ou des sauvegardes historiques.

- Mise à niveau attestée de `0008` vers `0017`, manifeste et smoke tests PASS ;
  release du pilote `/opt/oip/releases/m7c1-1`.
- Worker ponctuel `--once` : `COMPLETED`, observation HTTP 200, 20 788 octets,
  117 caractères extraits, `FIRST_SEEN`. Cela prouve un passage, pas une veille
  durable, un changement entre deux observations ou une absence de fuite.
- Après le pilote : API indiquant `MANUAL=false TOR=false`, Tor arrêté ; pas
  d'inventaire final indépendant attestant l'arrêt de tous les workers.
- Profil privé, santé, disponibilité, UI et refus anonyme testés PASS dans les
  sorties historiques. Moniteur en échec avec Tor actif, sain après son arrêt.
- Sauvegardes hors site automatiques : `NOT_ENABLED`. Restauration externe
  effective non suffisamment établie par les pièces relues.
- Autorisation OVH déclarée reçue par l'opérateur ; justificatif et portée non
  contrôlés dans cette reprise. OIDC/MFA, scheduler et collecte permanente non
  attestés actifs. État actuel des conteneurs, versions, ports et données inconnu.

## 7. Écarts documentaires traités et dettes conservées

| Écart | Traitement de stabilisation |
|---|---|
| README empilant les lots et « non déployé » | Remplacé par portail vers les deux références ; guides de détail conservés |
| Architecture/API historiques : head `0008`, docs gateway accessibles, absence de scheduler | Balisés historiques ; état courant ci-dessus : head `0017`, docs masquées, scheduler présent opt-in |
| Backlog OVH initial présentant tout M2–M7 comme restant | Balisé historique ; roadmap active unique avec preuves et dépendances |
| M7-C et M4-B annonçant PostgreSQL jamais passé | Statuts historiques explicités ; résultats CI datés centralisés ici |
| Retry, purge ou notifications présentés comme étapes implicites | Aucun ajout automatique : pas de retry, purge absente, brouillons seulement |
| Manifeste du paquet confondu avec arbre stabilisé | Original conservé, manifeste courant distinct par sa provenance |
| Guide de reprise après crash antérieur aux baux | Ne pas suivre les anciennes commandes ; contrat M2-B/C et validation de runbook restant nécessaires |
| Versions et builds | Python sans lock transitif ; Node 24 en CI / 22 en Docker ; images mobiles : dette de reproductibilité |
| Auditeur historique recommandant une nouvelle racine | Conseil générique contraire à la stratégie acceptée ; conserver historique et références, ne pas l'appliquer |

Les migrations, tests historiques, scripts utiles, branches, tags et archives de
passation sont conservés. Aucun nettoyage de base, suppression d’archive locale, import de M7-C2/C3/C4,
déploiement, activation Tor/worker/scheduler ou lecture de secret/donnée réelle
n’est réalisé. Les commits sources/documentaires sont publiés sur les branches
de travail après audits ; le seul accès OVH ultérieur est le tunnel autorisé décrit
ci-dessus. Pour les choix et la suite, voir la
[roadmap et le registre des décisions](ROADMAP_ET_DECISIONS.md).
