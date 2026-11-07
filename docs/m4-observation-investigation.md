# M4-A — Recherche d'observations et provenance (hors production)

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 retient le jeton API individuel pour l’administration et
> une vitrine visiteur en lecture seule. Leur mise en œuvre est décrite dans
> l’état de référence. Ce guide n’autorise aucune action OVH.

## Périmètre livré

Ce lot ajoute une **recherche documentaire sur les métadonnées déjà retenues** et une vue de provenance en lecture seule. Il n'augmente **pas** la quantité de contenu d'une page stockée : le texte temporaire extrait et le HTML restent éphémères.

- `GET /api/v1/observations/search` : pagination bornée (1–100, offset ≤ 10 000), filtres `source_id`, `category` (catégorie du registre **source**, et non catégorie CTI), `change_status`, `since` inclus, `until` exclu, `sha256` exact, et `q` (titre/description uniquement).
- `GET /api/v1/observations/{id}/provenance` : observation, identifiant et état du job, source, comparaison avec l'observation précédente **de la même source**, champs modifiés et empreinte de texte. Le classement est déterministe `(created_at DESC, id DESC)`.
- `GET /api/v1/observations/retention/preview?older_than_days=90` : **ADMIN** uniquement, estime le volume d'observations antérieures au seuil. Aucune suppression ni migration de purge.
- L'interface **Observations** propose les filtres, la pagination et une comparaison en fenêtre modale.

`q` est analysé en recherche plein texte PostgreSQL (`simple` + `plainto_tsquery`) avec un index GIN ajouté par `0011_observation_metadata_fts`. Le fallback SQLite utilisé dans les tests est une recherche littérale insensible à la casse ASCII via `LIKE` échappé : les résultats peuvent donc différer entre SQLite et PostgreSQL pour certains termes. L'index PostgreSQL ne porte que sur `title` et `description`, jamais sur le contenu intégral.

## Limites et précautions

- **Aucun diff sémantique du corps de page n'est possible** après collecte : seul son hash SHA-256 et sa longueur sont stockés. Un changement de hash ne prouve ni menace ni véracité du contenu.
- Aucun score de confiance n'est calculé sur une observation brute. Les classifications CTI, si présentes, sont des objets distincts avec leur propre niveau de confiance.
- Aucun archivage HTML ni création de copies de données n'est introduit ; pas de nouveaux fetchs, ni de planification activée.
- La comparaison de deux observations contient les champs de métadonnées déjà persistés ; elle ne constitue pas une preuve d'activité criminelle.
- Les limites de pagination bornent l'utilisation de l'API, mais l'implémentation `OFFSET` doit être profilée sur PostgreSQL avant montée en charge.
- La création de l'index GIN peut provoquer des verrous et une charge d'I/O sur une base existante ; tester sur PostgreSQL réel en préproduction, avec une fenêtre de maintenance et une restauration vérifiée.
- La recherche ne couvre pas les observations supprimées, ni les sources supprimées physiquement. Le nettoyage et la rétention automatisés nécessitent une étude de dépendances (`KeywordMatch`, `ClassificationResult`, `ThreatIndicator`, `Alert`, `Report`, `AuditLog`) et restent **hors lot**.

## Vérifications locales (ne touche pas au VPS)

```bash
cd backend
PYTHONPATH=. pytest -q tests/test_m4_observations.py tests/test_m4_migration.py
# SQLite temporaire uniquement ; aucun contact avec Tor
cd ../frontend
npm ci --ignore-scripts
npm run typecheck && npm run build && npm run test:unit
```

Les tests avec PostgreSQL réel restent à exécuter dans un environnement isolé avant tout déploiement. **N'exécute pas `alembic upgrade head` sur `vps-ovh` sans dump local avant migration vérifié**. Ce paquet ne doit pas remplacer le code de production actuel ; les jalons M2/M3 non déployés restent des dépendances.

## Prochain travail (M4-B)

Concevoir une indexation *explicite, limitée, minimisée* si la recherche dans une fraction du texte s'avère nécessaire, avec classification de sensibilité préalable, durée de rétention définie et validation humaine. En parallèle : tests PostgreSQL sur volumes représentatifs et politique de purge avec audit et restauration contrôlés. Aucune collecte réseau réelle n'est nécessaire.
