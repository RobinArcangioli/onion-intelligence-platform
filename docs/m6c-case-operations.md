# M6-C — Politiques de notification locales et rapport opérationnel

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 prévoit un admin connecté par mot de passe et une vitrine
> visiteur limitée ; ce modèle n’est pas encore implémenté. Ce guide
> n’autorise aucune action OVH.

**Version : incrément expérimental hors production, depuis M6-B.**

## Conception et périmètre

M6-C introduit la migration additive `0017_case_notification_drafts`, le module `app.api.case_operations` et l'écran **Opérations** (rôles ANALYST/ADMIN). OIP ne possède **aucun canal de livraison** (pas d'email, webhook, SMTP, queue de dispatch, cron ou scheduler). L'activation d'une politique **autorise uniquement la préparation manuelle d'un instantané local**. Un enregistrement `NOT_SENT` n'est ni un envoi, ni un accusé de réception.

Les politiques sont créées `approved=false`, `enabled=false`, sans destinataire. Seul `ADMIN` peut créer, approuver, activer, suspendre ou révoquer une politique, par contrôle de version. Toute transition de politique est auditée. Un acteur ANALYST/ADMIN peut préparer une notification **en une action explicite** uniquement si la politique est approuvée et activée, que le statut cible correspond exactement et que la priorité est supérieure ou égale au seuil. Les contenus sont des champs codifiés : identifiant de dossier, version, statut, priorité, code de politique et identifiant de modèle. Les notes, contenus de collecte, IOC, identité du responsable, URL et destinataires ne sont jamais copiés.

Une contrainte d'unicité SQL (`policy_id`, `case_id`, `case_version`) empêche deux préparations identiques, y compris sous concurrence. Une nouvelle version du dossier nécessite une préparation séparée. La politique peut être suspendue sans affecter les instantanés déjà présents ; ceux-ci restent `NOT_SENT` et ne seront pas transmis. Les vérifications PostgreSQL réelles de concurrence et de charge restent à faire.

## API (authentification nominative OIP obligatoire)

| Méthode | Route | Rôle minimal | Action |
|---|---|---|---|
| POST | `/api/v1/case-operations/policies` | ADMIN | Créer un code (3–32 caractères majuscules, chiffres, `_`), statut cible et priorité minimale ; désactivée initialement. |
| GET | `/api/v1/case-operations/policies` | ANALYST | Voir au plus 100 politiques. |
| PATCH | `/api/v1/case-operations/policies/{id}` | ADMIN | `expected_version`, `approved`, `enabled` ; conflit `409` si version obsolète. |
| POST | `/api/v1/case-operations/drafts` | ANALYST | Préparer `case_id`, `policy_id`, `expected_case_version`, sans transmission ; doublon `409`. |
| GET | `/api/v1/case-operations/drafts` | ANALYST | Consulter les instantanés locaux paginés, filtre `case_id`. |
| GET | `/api/v1/case-operations/summary` | ANALYST | Agrégats par statut et priorité ; dossiers ouverts non assignés ; brouillons non envoyés. |
| GET | `/api/v1/case-operations/summary/export?format=json\|csv` | ANALYST | Télécharger uniquement les agrégats, entêtes anti-cache, pas de noms, URL, notes ni indicateurs. |

Le endpoint historique `GET /api/v1/cases/{id}/notification-preview` de M6-B reste une simulation `DISABLED` : son contrat n'a pas été modifié.

## Schéma et retour arrière

Deux nouvelles tables : `case_notification_policies` et `case_notification_drafts`, cette dernière référençant `analyst_cases`. Aucune colonne, contrainte ou donnée existante n'est modifiée. Le `downgrade` **détruit les deux nouvelles tables** ; il ne doit pas être appliqué sur production sans plan de récupération et sauvegarde restaurée. Ces objets ajoutent des dépendances aux dossiers qui devront être prises en compte avant toute purge future.

## Validation hors production

Depuis `backend/`, dans un environnement Python possédant les dépendances de développement :

```bash
python -m pytest -q tests/test_m6c_notifications.py tests/test_m6c_migration.py
python -m pytest -q tests   # autorisé à être réparti en groupes si nécessaire
```

Depuis la racine :

```bash
python -m pytest -q deploy/ovh/tests
cd frontend && npm ci && npm run build && npm run test:unit
```

Le test de migration crée une base **SQLite jetable** dans le dossier temporaire de pytest, puis effectue `0016 → head → 0016`, et vérifie qu'une source synthétique reste intacte. Ce n'est **pas** une preuve de compatibilité avec PostgreSQL 17.

Pour la recette PostgreSQL 17, utiliser une instance jetable dédiée, non reliée à `vps-ovh`. Tester au minimum : migrations `0008 → 0017`, sauvegarde/restauration, approbation, révo­cation, concurrence sur version de politique, doublons lors de la création des brouillons, intégrité des clés étrangères, volumétrie, export CSV/JSON. Aucun réseau Onion nécessaire.

## Prérequis de production / décisions GO-NO-GO

**NO-GO actuellement** : tests de concurrence PostgreSQL 17 réels et restauration pré-migration non attestés pour cette chaîne de migrations. Ne pas installer ni exécuter `alembic upgrade head` sur le VPS pilote. Aucune publication GitHub automatique. Tor et la planification restent désactivés.

**GO développement** : examen, tests locaux et recette sur base synthétique jetable. Toute future livraison externe est un nouveau changement fonctionnel : elle demandera un modèle de menace, une gouvernance des destinataires, un contrôle explicite, gestion des échecs et des secrets, puis une recette spécifique. Ne pas transformer silencieusement les brouillons de M6-C en messages à transmettre.
