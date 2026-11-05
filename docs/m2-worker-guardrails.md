# M2-A — File de collecte : garde-fous sans migration

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 prévoit un admin connecté par mot de passe et une vitrine
> visiteur limitée ; ce modèle n’est pas encore implémenté. Ce guide
> n’autorise aucune action OVH.

Ce lot est **du code source à tester hors production**, pas une instruction pour activer Tor. Le VPS OVH reste en profil `db + api + gateway`, avec `OIP_MANUAL_COLLECTION_ENABLED=false` et sans `tor`/`queue_worker`. Aucun schéma, migration, minuterie ou collecte réelle n'est ajouté. La politique contractuelle du fournisseur doit être validée avant un pilote Tor.

## Améliorations

- **Délai global de la requête** : `collect_one()` applique une limite externe de 120 secondes au `fetcher`. Les délais `httpx` existants protègent déjà les périodes d'inactivité mais ne limitent pas la durée totale d'une réponse qui envoie périodiquement des octets. Si la requête dépasse le délai, le job finit `FAILED` avec `FETCH_TIMEOUT`, sans observation, retry automatique, URL ni corps HTML persisté. Le plafond concerne l'attente réseau et **non** les analyses et transactions ultérieures. Une coroutine qui ignore la cancellation peut dépasser la limite : à traiter lors du jalon leases/heartbeats.
- **Inspection sans mutation** : `python -m app.collector.worker --inspect-stale` retourne seulement `stale_running_jobs=N`. Mode SQL local, sans contact Tor, indépendant du switch de collecte. L'inspection est instantanée et peut différer d'une récupération effectuée plus tard si les jobs changent.
- **Récupération explicite** : `python -m app.collector.worker --recover-stale --confirm-worker-stopped` clôt les anciens `RUNNING` (>60 minutes par défaut) avec `WORKER_INTERRUPTED` et audit, jamais de relance/requête réseau. L'opérateur **doit effectivement arrêter tous les workers/collecteurs avant l'attestation** ; l'option ne vérifie pas cet arrêt. Opération uniquement en maintenance, avec sauvegarde vérifiée avant usage sur une base de production. Le seuil `--stale-minutes` accepte 1 à 10080.

## Tests hors réseau

```bash
python -m pytest -q -p no:cacheprovider backend/tests/test_m2_worker_guards.py
python -m pytest -q -p no:cacheprovider backend/tests
python -m unittest discover -s deploy/ovh/tests -q
python scripts/ci-index-audit.py
```

Tous les tests utilisent SQLite, de faux fetchers asynchrones et des adresses Onion synthétiques ; aucun appel réseau ou Tor n'est nécessaire. Le contrôle d'index nécessite un vrai dépôt Git.

## Préparation GitHub

Le dépôt `RobinArcangioli/onion-intelligence-platform` a été constaté **public** le 24 octobre 2026, mais n'inclut pas nécessairement les commits OVH/M1. Ne pas pousser automatiquement cet incrément, ses ancêtres, ou un workflow qui inclurait des secrets de production.

Avant une contribution : faire l'inventaire de la branche distante, vérifier le statut de la licence, inspecter les fichiers et l'historique avec `python scripts/pre-push-audit.py`, et ne traiter l'option `--allow-historical-notes` que comme **acceptation explicite du risque documentaire** après revue humaine (elle ne masque pas les détections de secrets). Ne jamais `git push --force`, changer la visibilité, ni automatiser le déploiement OVH sur simple PR. CI : lecture seule, aucune variable d'environnement de production. Le propriétaire choisira la branche de publication et sa stratégie Git.

## Limites / suite M2

Ce lot ne résout **pas** la reprise automatique après crash, le leasing distribué, les heartbeats, les retries bornés, la concurrence multi-worker, l'annulation administrative ou la protection contre les tâches CPU coûteuses. Ces fonctions demandent une conception de schéma/versions et une sauvegarde/restauration vérifiée avant déploiement. Le récupérateur manuel actuel peut entrer en conflit avec un worker actif : c'est pourquoi son arrêt est un prérequis bloquant.

**GO pour les tests locaux et la revue du patch. NO-GO pour déployer sur le VPS, lancer Tor ou modifier PostgreSQL.**
