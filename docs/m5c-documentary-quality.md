# M5-C — Qualité documentaire CTI et cooccurrences contrôlées

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 retient le jeton API individuel pour l’administration et
> une vitrine visiteur en lecture seule. Leur mise en œuvre est décrite dans
> l’état de référence. Ce guide n’autorise aucune action OVH.

**Statut : développement et recette locale uniquement.** Ce module n'autorise aucune collecte, recherche DNS, enrichissement en ligne, notification, export ou modification du VPS. Il est **en lecture seule** et n'ajoute aucune migration au-delà de `0014_ioc_candidates` (M5-B).

## Objectifs et vocabulaire

OIP conserve des mentions documentaires et des références publiques, **pas une preuve d'exploitation ou d'intrusion**. Trois axes restent indépendants :

- `original_confidence` : confiance du classifieur/extracteur d'origine, inchangée par la revue ;
- `documentary_quality` : indice de *complétude et fraîcheur de la mention*, calculé à la lecture, de 0 à 100 ; il ne mesure ni dangerosité, ni risque, ni valeur de compromission ;
- `analyst_priority` : jugement humain séparé (`UNASSESSED`, `LOW`, `MEDIUM`, `HIGH`), sans conversion automatique en score numérique.

**Rubrique versionnée :** `M5C_MENTION_QUALITY_V1`.

1. Initialiser avec `max(0, min(100, original_confidence))`.
2. `PENDING` plafonne à 60 ; `ACCEPTED` ajoute 10 avec plafond 90 ; `REJECTED` vaut 0. *ACCEPTED signifie « mention examinée », jamais « attaque confirmée ».*
3. Ancienneté depuis `created_at` de la mention : moins de 30 jours = `CURRENT` ; 30–89 jours = `AGING`, plafond 50 ; 90 jours ou plus = `STALE`, plafond 30. Une date future est ramenée à zéro jour d'âge. Les horodatages SQLite anciens sans fuseau sont interprétés en UTC.
4. Exposer les codes d'explication (`EXTRACTION_CONFIDENCE_ONLY`, `REVIEW_PENDING`, `MENTION_REVIEWED`, `REJECTED_MENTION`, `OLDER_THAN_30_DAYS`, `OLDER_THAN_90_DAYS`, `OBSERVED_WITHIN_30_DAYS`). La réponse précise la version de rubrique et son domaine de validité.

Ce score est une **heuristique de triage**, non calibrée statistiquement et non validée sur un corpus indépendant. Les seuils doivent être réexaminés par des analystes avant toute automatisation future.

## API et RBAC

Toutes les routes exigent un jeton valide et le rôle `ANALYST` ou `ADMIN`. Les comptes `VIEWER` reçoivent 403.

- `GET /api/v1/cti/quality-preview?kind=IOC|CVE&review_status=...&limit=30&offset=0` : tri par date/id, page de 1 à 50 éléments, `offset ≤ 10000`. Lecture seule, valeur IOC visible uniquement aux analystes. Ne stocke aucun résultat recalculé.
- `GET /api/v1/cti/cve-ioc-links?reference=CVE-2025-12345&indicator_type=DOMAIN&limit=30` : affiche uniquement les paires **référence CVE acceptée + mention IOC acceptée dans une *même observation et source***. Rejette les filtres CVE invalides. `source_count` dénombre des sources différentes, **pas des preuves indépendantes**. Une paire n'indique pas que l'IOC exploite la CVE. Les valeurs ne sont ni résolues ni vérifiées à distance.
- `GET /api/v1/cti/review-history/IOC|CVE/{id}?limit=30` : historique des décisions de revue réellement présentes dans `audit_logs`, filtrées par action et type. Métadonnées renvoyées via liste blanche : identifiant d'audit, opérateur, date, décision, priorité et code de motif IOC. **Aucune justification CVE libre, valeur IOC, contenu original, HTML ni identifiant de jeton** n'est renvoyé. Une seule décision est actuellement permise par la politique de revue ; la route ne prétend pas créer un historique d'éditions multiples.

L'interface CTI ajoute « Qualité documentaire » et « Liens CVE/IOC » et une fenêtre d'audit contextualisée. L'interface ne charge ces informations qu'avec un rôle permettant l'accès.

## Garanties et limites

- Les nouvelles routes sont **GET uniquement**, aucun appel réseau externe, aucune écriture SQL ou recalcul persistant ; la création d'IOC demeure `opt-in` sous M5-B et Tor reste désactivé.
- Pas de déduction de malveillance, de vecteur d'exploitation, d'attribution ni de CVSS ; une cooccurrence dans la même page n'implique aucune relation causale.
- La qualité est calculée selon l'horloge de l'API à chaque lecture : les scores peuvent baisser dans le temps sans événement en base. Les systèmes de comparaison doivent conserver `rubric_version` et le contexte temporel.
- La confidentialité des valeurs IOC demeure sensible ; les journaux et exports ne doivent pas inclure les payloads. L'accès local/privé de l'UI reste nécessaire.
- Regroupements SQL et pagination exécutés localement avec SQLite dans les tests ; le coût des agrégations et la compatibilité **PostgreSQL 17 doivent être vérifiés dans une base jetable**. Aucune recette sur Tor réel n'est effectuée.
- Les suppressions et les exports externes restent interdits. Aucune politique de rétention n'est appliquée.

## Recette hors production

```bash
PYTHONPATH=backend python3 -m pytest -q backend/tests/test_m5c_quality_context.py
PYTHONPATH=backend python3 -m unittest discover -s deploy/ovh/tests -q
(cd frontend && npm run build && npm run test:unit)
python3 scripts/verify-manifest.py
python3 scripts/pre-push-audit.py --no-history
```

**Production : NO-GO.** Le VPS doit conserver M1, sans M2–M5. Les migrations existantes jusqu'à `0014` attendent une recette PostgreSQL 17, des tests de concurrence et une restauration indépendante vérifiée. Les sauvegardes automatisées restent reportées sur demande du propriétaire ; cela ne justifie aucune migration en production.
