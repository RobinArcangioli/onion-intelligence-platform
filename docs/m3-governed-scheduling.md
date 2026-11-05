# M3 — Surveillance récurrente gouvernée (hors production)

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 prévoit un admin connecté par mot de passe et une vitrine
> visiteur limitée ; ce modèle n’est pas encore implémenté. Ce guide
> n’autorise aucune action OVH.

**État : code préparé localement, activation interdite sur le VPS OVH actuel.**
Aucune connexion Tor n'a été tentée. Les sauvegardes automatisées restent reportées
à la demande du propriétaire. La migration `0010_governed_schedules` ne doit PAS
être appliquée sur la base OVH avant sauvegarde externe, restauration éprouvée,
recette PostgreSQL et conformité fournisseur.

## Contrats d'exécution

- **Double verrou global, désactivé par défaut :** `OIP_SCHEDULER_ENABLED=false`
  ET `OIP_MANUAL_COLLECTION_ENABLED=false`. Les deux doivent être explicitement
  `true` sur le service du scheduler (et l'admission API / worker configurées et
  autorisées séparément). La politique `OIP_COLLECTION_EMERGENCY_STOP=true`
  reste prioritaire. Aucun scheduler ne démarre avec Compose par défaut :
  service `scheduler`, profil **`scheduled`** (distinct du profil Tor).
- **Opt-in individuel :** `ADMIN` fournit une référence d'autorisation,
  justification, expiration future (maximum 90 jours), fréquence entre 60 et
  10 080 minutes, fenêtre UTC sans chevauchement minuit (début 0–23, fin 1–24),
  budget quotidien de 1 à 24 jobs. `enabled` est un champ obligatoire de PUT ;
  aucun modèle/seed n'ajoute de planning implicite. L'approbation générale de
  source et `collection_enabled` restent nécessaires. Les découvertes Onion
  ne deviennent jamais des sources automatiquement.
- **Un seul GET, non effectué par le scheduler :** le service de planification
  effectue uniquement des opérations SQL. Il dépose des jobs `PENDING` selon
  les règles M2 ; le worker les prend en charge indépendamment si l'opérateur
  a activé le profil Tor conformément au contrat et aux tests réseau.
- **Mécanismes anti-surcharge :** un job actif maximum par source, plafond global
  M2 des jobs en attente, cooldown de source, circuit breaker, budget journalier
  UTC, fenêtre horaire, expiration et prochain créneau prévu. Les décisions
  `ENQUEUED`, `ACTIVE_JOB`, `GLOBAL_QUEUE_FULL`, `SOURCE_RESTRICTED`,
  `DAILY_BUDGET`, `OUTSIDE_WINDOW`, `SOURCE_DISABLED` et `APPROVAL_EXPIRED`
  sont tracées en DB. Aucun réessai automatique d'un job échoué.
- **Fencing de l'autorisation :** le worker refuse un job issu du scheduler
  si la planification a été suspendue ou expirée entre son dépôt en file et sa
  prise en charge. La suspension ne peut pas annuler rétroactivement un fetch
  déjà lancé : arrêter le worker pour interrompre les traitements en cours.
- **Traçabilité :** chaque décision conserve un instantané de la référence
  d'autorisation et de sa date d'expiration, le job éventuel, l'heure et le motif.
  Les changements ADMIN ont une identité et une justification dans `audit_logs`.

## API réservée à ADMIN

| Méthode | Endpoint | Effet |
| --- | --- | --- |
| `GET` | `/api/v1/schedules/{source_id}` | Lire une configuration existante |
| `PUT` | `/api/v1/schedules/{source_id}` | Créer / modifier, opt-in explicite avec justification |
| `POST` | `/api/v1/schedules/{source_id}/pause` | Suspendre toute future admission programmée |
| `GET` | `/api/v1/schedules/{source_id}/decisions?limit=50` | Lire les décisions DB, au plus 100 |

L'interface **Sources Onion > Planning** apparaît aux administrateurs.
L'activation visuelle d'une source ne démarre ni le service scheduler, ni Tor.
Toutes les plages horaires sont exprimées en **UTC**.

## Recette locale (DB uniquement, sans Tor)

```bash
cd backend
python -m pytest -q tests/test_m3_governed_schedules.py tests/test_m3_migration.py
python -m pytest -q tests/test_m2_lease_heartbeats.py tests/test_m2c_collection_resilience.py
cd ../frontend
npm ci --ignore-scripts
npm run test:unit
npm run build
```

Le mode `python -m app.scheduler.cli once` est sûr **si les verrous sont à false**,
mais une base existante et ses secrets doivent être fournis pour tout test
`true`. Ne pas exécuter cette dernière configuration sur OVH à ce stade.

## Tests à effectuer avant GO de déploiement

1. Sauvegarde chiffrée hors VPS et restauration réellement testée pour la
   version de la base à mettre à jour ; maintenance et rollback documentés.
2. `alembic upgrade 0010_governed_schedules` sur **PostgreSQL 17 de staging**
   avec enregistrements réels anonymisés ; tester le retour arrière **sur une
   copie uniquement** (`downgrade` supprime définitivement les planifications
   et leurs décisions).
3. Plusieurs sessions PostgreSQL / instances scheduler simultanées : vérifier
   zéro double job, quotas globaux, blocage transactionnel, pause/révocation
   concomitante, perte de connexion et redémarrage.
4. Vérifier l'intégration dans la CI, tests UI/Playwright et le paramétrage
   réseau avec Tor **uniquement après accord écrit du fournisseur**.
5. Tester le stop coordonné : `OIP_SCHEDULER_ENABLED=false`, arrêt du service
   scheduler et des workers, refus des nouveaux jobs, revue des `PENDING` et
   `RUNNING` avant toute reprise.

**Ne pas déployer cette migration ni activer le profil scheduled sur vps-ovh.
Pas de publication GitHub automatique.**
