# M4-B — Recherche indexée et évaluation d'impact de rétention

## Périmètre effectif

M4-B est une **livraison de développement hors production** fondée sur M4-A. Elle n'active ni Tor ni collecte, ne conserve aucun texte de page supplémentaire et n'offre aucune route de suppression. La base OVH n'est pas modifiée.

### Recherches

- `GET /api/v1/observations/search` conserve les mêmes filtres et bornes M4-A (`limit` 1–100, `offset` ≤ 10 000) et le tri déterministe `(created_at DESC, id DESC)`.
- Sans filtre `category`, le calcul du `total` évite la jointure avec `onion_sources`. La requête paginée joint toujours le registre pour afficher nom/catégorie.
- La migration **`0012_observation_read_indexes`** ajoute des index B-tree pour le tri global, le tri par source et les recherches par hash avec tri ; ainsi que deux index utiles aux références vers une observation (`alerts.observation_id`, `audit_logs.entity_id`). Le GIN de `0011` demeure inchangé.
- Un index ne constitue **pas** une preuve de performance : le plan réel et les coûts disque/I/O doivent être relevés sur PostgreSQL 17 avant tout déploiement. Des filtres combinés peuvent toujours entraîner une étape `Sort`, et les recherches `OFFSET` profondes ne sont pas optimisées par ce lot.

### Simulation de rétention (jamais de purge)

`GET /api/v1/observations/retention/preview?older_than_days=90&source_id=<uuid optionnel>` (rôle `ADMIN`) retourne :

- `observation_count` : nombre d'observations avant la date limite en UTC ;
- `dependent_row_counts` : lignes liées via `observation_id` (correspondances, classifications, indicateurs, alertes), et références d'audit dont `entity_id` correspond à ces observations ;
- `report_snapshots_not_resolved` : nombre **global** de rapports dont les instantanés JSON ne peuvent pas être attribués de manière fiable à chaque observation (même en filtrant par source) ;
- `dry_run: true`, `deletion_enabled: false`, `safe_to_purge: false` ; blocages explicites.

**Ne pas additionner les compteurs de dépendances pour déduire un nombre d'observations distinctes** : une observation peut avoir plusieurs lignes liées. Les détails d'audit non structurés et les instantanés de rapports peuvent conserver d'autres références invisibles à ces comptes. L'absence de relation détectée **n'autorise aucune suppression**.

## Proposition de politique de conservation — NON approuvée

| Catégorie | Piste de décision avant approbation | État |
|---|---|---|
| Observations minimales | Période à définir par le propriétaire (simulation de 90 jours par défaut, **pas une règle de purge**) ; revoir les obligations légales et besoins CTI | Aucun effacement |
| Dérivés CTI et alertes | Préserver leur traçabilité avec l'observation d'origine ; définir revue et clôture avant effacement | Aucun effacement |
| Rapports JSON | Revue spécifique des liens de provenance et de leur rétention | Aucun effacement |
| Journal d'audit | Conservation séparée et contrôles d'intégrité ; jamais une suppression en cascade aveugle | Aucune purge |
| Données minimisées | Aucun HTML/corps de page brut stocké ; voir guide M4-A pour limites des empreintes | Inchangé |
| Sauvegardes et reprises | Décider durée de conservation, chiffrement, dépôt hors VPS, et test de restauration avant migrations en production | Reporté par le propriétaire |

Une future purge nécessitera une politique approuvée, une analyse exhaustive des références non relationnelles, des règles RGPD adaptées au traitement, une procédure de suppression testée, une preuve de restauration et des journaux d'audit. **Aucun mécanisme d'effacement n'est inclus ici.**

## Contrôles reproductibles, hors OVH

```bash
cd backend
python -m pytest -q tests/test_m4b_retention.py tests/test_m4b_migration.py
python -m pytest -q tests/test_m4b_postgres17.py  # SKIP si aucun serveur de test
```

Pour **exécuter réellement** le scénario PostgreSQL 17, utiliser un poste de développement doté de Docker, et une base **jetable, vide, en boucle locale**, nommée exactement `oip_m4b_test` :

```bash
docker run --rm -d --name oip-m4b-pg17 \
  -e POSTGRES_USER=oip_test \
  -e POSTGRES_PASSWORD=local_ci_fixture_only \
  -e POSTGRES_DB=oip_m4b_test \
  -p 127.0.0.1:55432:5432 postgres:17-alpine
# attendre que le conteneur soit prêt (pg_isready), puis, depuis backend :
PG_TEST_PASSWORD=local_ci_fixture_only
OIP_M4B_TEST_DSN="postgresql+psycopg://oip_test:${PG_TEST_PASSWORD}@127.0.0.1:55432/oip_m4b_test" \
  python -m pytest -q -s tests/test_m4b_postgres17.py
# stoppe et supprime UNIQUEMENT ce conteneur jetable de tests
# docker stop oip-m4b-pg17
```

Les identifiants ci-dessus sont **fictifs et uniquement destinés au test local**. Le test refuse les hôtes autres que loopback, les paramètres URL spéciaux, les noms de base différents, une version autre que PostgreSQL 17 et une base déjà non vide ; il effectue ensuite migrations, recherche FTS, vérification d'index et `EXPLAIN (ANALYZE, BUFFERS)` sur **400 observations synthétiques**. Il ne fixe pas de SLO à partir de ce petit échantillon. Il doit être exécuté sur une base de test fraîche à chaque fois.

La CI possède un job `postgres17-m4b` séparé, sans secret de production ni déploiement, qui utilisera une base jetable en conteneur. **Tant que cette CI n'est pas publiée et exécutée, ces tests PostgreSQL ne sont pas attestés comme réussis.**

## Conditions GO/NO-GO pour OVH

**GO développement :** suite backend, migrations SQLite de test, contrôles RBAC et index. **NO-GO production :** absence de sauvegarde externe restaurée/validée, tests PostgreSQL 17 et multi-workers hors production, revue des plans `EXPLAIN`, fenêtre de maintenance et gestion de rollback. Ne pas exécuter `alembic upgrade head` sur `vps-ovh` : cela appliquerait aussi les migrations M2, M3, M4-A et M4-B non encore livrées en production.
