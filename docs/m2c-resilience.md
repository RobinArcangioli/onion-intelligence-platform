# M2-C — Admissions bornées, circuit breaker, arrêt d'urgence et métriques

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 prévoit un admin connecté par mot de passe et une vitrine
> visiteur limitée ; ce modèle n’est pas encore implémenté. Ce guide
> n’autorise aucune action OVH.

**Statut : code hors production.** Ce lot n'active **ni Tor, ni ordonnanceur, ni
réessais automatiques**. Sur le VPS OVH actuel, conserver le déploiement privé
sans profils Tor. Les sauvegardes automatisées et la recette PostgreSQL réelle
restent à faire avant toute migration/activation de collecte.

## Comportement

| Contrôle | Défaut | Portée |
|---|---:|---|
| `OIP_COLLECTION_SOURCE_COOLDOWN_SECONDS` | 300 | Une même source ne peut être remise en file immédiatement après son dernier job. `0` autorise un second clic sans délai, mais pas deux jobs actifs. |
| `OIP_COLLECTION_MAX_PENDING` | 25 | Plafond global de jobs `PENDING` ; refus HTTP `429 GLOBAL_QUEUE_FULL`. |
| `OIP_COLLECTION_MAX_RUNNING` | 2 | Plafond global de jobs `RUNNING` au moment de l'attribution ; les jobs en trop restent `PENDING`. |
| `OIP_COLLECTION_CIRCUIT_FAILURES` | 3 | Nombre consécutif d'échecs réseau sur une même source pour ouvrir le circuit. |
| `OIP_COLLECTION_CIRCUIT_OPEN_SECONDS` | 3600 | Délai avant une nouvelle **requête manuelle** après ouverture ; aucun réessai automatique. |
| `OIP_COLLECTION_EMERGENCY_STOP` | false | Quand `true`, bloque les nouvelles admissions API et workers. Recréer les conteneurs si la variable est changée dans `.env` après leur démarrage. |
| `OIP_COLLECTION_KILL_FILE` | `/tmp/oip-collection.disabled` | Sentinelle contrôlée dans le conteneur concerné à chaque admission et heartbeat ; elle n'est **pas automatiquement partagée** entre API et worker. |

Valeurs configurées par environnement/Compose, soumises à des bornes strictes.
Une politique invalide interdit les nouvelles admissions ; la configuration
du worker est considérée défaillante. Les sources doivent toujours être
explicitement autorisées et rester `collection_enabled`.

### Sérialisation PostgreSQL

Les admissions utilisent un verrou transactionnel PostgreSQL commun avant les
contrôles de compteurs globaux ; l'API prend ensuite le verrou de source, et le
worker le verrou du job puis de la source. Les index et jetons de bail M2-B
restent applicables. **La recette de concurrence PostgreSQL multiworker reste
obligatoire** avant de revendiquer un contrôle global prouvé en production.
Les tests SQLite existants ne reproduisent pas `SKIP LOCKED`/les verrous PG.

### Circuit breaker

Les derniers jobs d'une source sont examinés. Si les N derniers se sont
terminés par `FAILED` et un code `TOR_NETWORK_ERROR`, `FETCH_TIMEOUT` ou
`COLLECTION_FAILED`, un nouvel enqueue est rejeté jusqu'à ce que le délai soit
écoulé depuis la fin du dernier échec. Le retour à l'état normal nécessite un
**nouveau clic humain** : rien n'est reprogrammé automatiquement. Un succès
rompra la série. Les autres erreurs ne sont pas présumées des indisponibilités
réseau ; elles ne provoquent pas un circuit de ce type.

## Arrêt d'urgence (lorsque Tor sera contractuellement autorisé)

1. **Stop immédiat prioritaire** : arrêter les services concernés et empêcher
   tout redémarrage automatique, selon le runbook de l'environnement. À titre
   d'exemple, depuis la racine du projet avec la configuration exacte utilisée
   pour les démarrer :
   `docker compose --profile tor stop queue_worker collector`.
2. Désactiver l'admission API (`OIP_MANUAL_COLLECTION_ENABLED=false`) et définir
   `OIP_COLLECTION_EMERGENCY_STOP=true`, puis redémarrer **uniquement les
   services concernés** selon une procédure validée. Les variables d'environnement
   déjà chargées ne se mettent pas à jour automatiquement.
3. Pour demander l'annulation d'une collecte dans un `queue_worker` vivant,
   créer la sentinelle dans son `/tmp` :
   `docker compose --profile tor exec -T queue_worker sh -c 'touch /tmp/oip-collection.disabled'`.
   Cette commande ne bloque pas l'API et ne remplace pas l'étape 1.
   L'annulation coopérative intervient au heartbeat (20 s par défaut).
4. Les jobs `RUNNING` arrêtés peuvent rester bloqués : **ne pas les relancer**.
   Après arrêt attesté de **tous** les workers, inspecter puis utiliser
   `--recover-stale --confirm-worker-stopped` suivant le runbook M2-B.
5. Ne reprendre qu'après examen de l'incident, autorisation de la source,
   contrôle des fuites réseau et approbation explicite.

Le verrou empêche la conservation des observations si la sentinelle est vue
avant finalisation, mais aucun dispositif ne peut annuler rétroactivement un
fetch déjà transmis. Pour une réaction immédiate, arrêter le conteneur.

## Métriques

`GET /api/v1/collection/metrics` exige **ADMIN** et le jeton habituel.
Réponse sans URL, identifiant de source ou jeton :

```json
{
  "jobs": {"PENDING": 0, "RUNNING": 0, "COMPLETED": 0, "FAILED": 0},
  "failed_24h": 0,
  "oldest_pending_seconds": null
}
```

Pas d'endpoint Prometheus public et pas de port supplémentaire.
Ce sont des instantanés SQL ; pas une télémétrie historisée, pas un SLO.

## Tests locaux (zéro trafic Tor)

```bash
python -m pytest -q -c backend/pyproject.toml backend/tests
python -m unittest discover -s deploy/ovh/tests -q
python scripts/ci-index-audit.py
python scripts/pre-push-audit.py       # bloquant pour publication publique
```

### Acceptation avant toute promotion en environnement réel

- Contrôle PostgreSQL 17 multi-sessions pour admission parallèle, quota global,
  `SKIP LOCKED`, verrou transactionnel, crash worker et perte de bail.
- Rotation des secrets et restauration hors serveur vérifiées ; sauvegardes
  récurrentes encore **reportées à la demande du propriétaire**.
- Contrat fournisseur Tor clarifié par écrit, puis tests d'egress sur hôte cible.
- Vérification API 429/503, métriques ADMIN et procédure d'arrêt/récupération.
- Aucune activation Tor sur OVH par ces scripts. Aucun patch n'est poussé
  automatiquement sur le dépôt public.
