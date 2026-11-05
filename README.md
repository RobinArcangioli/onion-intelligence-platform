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
**administrateur se connecte par mot de passe** ; une **vitrine visiteur** permet
aux clients de consulter certaines informations sur les dernières veilles, sans
accès aux fonctions ni aux informations sensibles. Ce modèle cible remplace la
proposition de suppression complète de l’authentification ; le code utilise
**encore des jetons et des rôles**. Les sauvegardes automatiques et une restauration
vérifiée sont des prérequis d’exploitation durable.

À la même adresse web, un petit lien **« accès visiteur »** ouvre la vue restreinte
sans connexion. Les dernières veilles affichent publiquement **date, statut,
volumes et noms des sources, sans adresse Onion**. L’admin peut également publier
explicitement certains rapports ; les autres informations restent internes.
Ces décisions sont actées dans la roadmap, mais ne sont pas encore implémentées.

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

Aucune licence open source n'est définie à ce stade. Le propriétaire reporte toute
décision de licence après le MVP ; elle ne fait pas partie de la roadmap active.
