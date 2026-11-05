# M6-B — Collaboration analyste, notes structurées et aperçu de notification

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 prévoit un admin connecté par mot de passe et une vitrine
> visiteur limitée ; ce modèle n’est pas encore implémenté. Ce guide
> n’autorise aucune action OVH.

**Statut : développement et tests hors production uniquement. NO-GO OVH.**

M6-B étend les dossiers M6-A existants, sans changer le statut de l'alerte
associée ni produire un diagnostic de compromission. Il ne comporte aucun
client d'envoi email/webhook, aucune nouvelle sortie réseau et aucune collecte
Tor. Les annotations ne doivent **jamais** contenir des extraits bruts de page,
des données personnelles, des informations d'authentification ou des IOC sensibles.
Les filtres techniques ne remplacent pas la politique humaine de saisie.

## Modèle et migration

La révision additive `0016_case_triage_notes` (après
`0015_analyst_cases`) ajoute :

- `analyst_cases.priority` : `UNASSESSED` (par défaut), `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` ;
  cette priorité de traitement analyste est indépendante de la priorité de
  l'alerte, du score de confiance CTI et du score CVSS ;
- `analyst_case_notes` : identifiant, dossier, version, acteur, catégorie, texte
  interne limité à 300 caractères et horodatage ; unicité `(case_id, case_version)`.

Les anciennes tables et les alertes ne sont pas modifiées. Les notes sont
créées en même temps que l'événement `NOTE` et l'entrée `AuditLog`, dans une
seule transaction, après `UPDATE ... WHERE version = expected_version` ;
une concurrence perdante reçoit `409` et ne laisse pas de note orpheline.
Le contenu de la note n'est **pas** recopié dans `AuditLog`, les événements
standardisés ou l'aperçu des notifications, mais **reste enregistré en clair
dans la base PostgreSQL** (donc accessible à ses administrateurs). Son exposition
via l'API reste réservée à `ANALYST`/`ADMIN`.

## API

Toutes ces routes utilisent l'authentification nominative existante et exigent
`ANALYST` ou `ADMIN` :

| Méthode | Route | Effet |
|---|---|---|
| `PATCH` | `/api/v1/cases/{id}` | `SET_PRIORITY` requiert `priority`; `ESCALATE` requiert `escalation_reason` ; autres transitions M6-A inchangées |
| `POST` | `/api/v1/cases/{id}/notes` | `201` après insertion atomique avec version attendue |
| `GET` | `/api/v1/cases/{id}/notes?limit=50&offset=0` | notes paginées, plus récentes d'abord |
| `GET` | `/api/v1/cases/{id}/notification-preview` | aperçu de données autorisées, **envoi toujours désactivé** |

Exemple de changement de priorité, données fictives :

```json
{"action":"SET_PRIORITY","expected_version":2,"priority":"HIGH"}
```

L'escalade exige l'un de ces motifs : `REVIEW_REQUIRED`, `TIME_SENSITIVE`,
`MULTI_SOURCE`, `OTHER`. Les motifs sont enregistrés dans les événements de
transition et dans l'audit sous forme de code. Un dossier `CLOSED` est terminal.

Exemple d'annotation interne :

```json
{"expected_version":3,"note_code":"FOLLOW_UP","body":"Vérifier la chronologie avec un second analyste."}
```

Catégories autorisées : `ANALYST_CONTEXT`, `FOLLOW_UP`,
`FALSE_POSITIVE_CHECK`, `ESCALATION_CONTEXT`. Les annotations sont limitées à
8–300 caractères, sans saut de ligne ni caractère de contrôle ; les motifs
contenant une URL explicite, un `.onion`, une adresse email ou certains mots
clés de secret sont refusés. **Ce filtrage est partiel**, notamment pour les
identifiants personnels non reconnus. Les messages ne doivent pas être
utilisés pour conserver du contenu collecté.

## Aperçu de notification : pas de canal sortant

L'aperçu renvoie `enabled=false`, `delivery=DISABLED`, `destinations=[]`,
`contents=METADATA_ONLY` et des éléments minimaux du dossier (identifiant,
statut, priorité, version). Il ne contient ni note, ni adresse, ni extrait,
ni corps d'alerte. Il ne transmet rien. Les futurs canaux et modèles seront
soumis à une politique d'approbation distincte (opt-in par ADMIN, secrets
externes, tests de fuite, rate limits, revue juridique et RGPD).

## Validations et limites

```bash
cd backend
python -m pytest -q tests/test_m6a_cases.py tests/test_m6b_case_collaboration.py tests/test_m6b_migration.py
cd ../frontend
npm run test:unit
npm run build
```

Les autres tests ont été exécutés par groupes sans contacter Tor.
Migration et downgrade répétés uniquement sur base SQLite jetable. Il manque
une validation sur **PostgreSQL 17 réel**, un test multi-API de concurrence,
une décision de rétention/purge des notes, des mesures de performance et une
restauration externe vérifiée avant tout déploiement OVH.

Le downgrade de `0016` **supprime toutes les notes et priorités** ; il est
interdit en production. Pour un futur retour arrière applicatif, conserver le
schéma et les données en place et ne rétablir le code précédent qu'après
vérification de compatibilité. Ne jamais utiliser la rétrogradation Alembic
comme stratégie de sauvegarde.
