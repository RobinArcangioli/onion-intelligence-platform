# M5-B — Candidats IOC documentaires, revue humaine et corrélation

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 retient le jeton API individuel pour l’administration et
> une vitrine visiteur en lecture seule. Leur mise en œuvre est décrite dans
> l’état de référence. Ce guide n’autorise aucune action OVH.

**Statut : développement hors production.** Cette fonctionnalité ne doit pas être activée sur `vps-ovh` tant que la migration `0014_ioc_candidates`, la reprise PostgreSQL 17 et le point de retour local avant migration ne sont pas validées. Les sauvegardes automatisées ont été reportées par le propriétaire ; aucune migration de production ne doit être tentée.

## Périmètre et minimisation

- Extraction locale **sans trafic réseau** à partir du texte éphémère de la seule page racine Onion explicitement autorisée à la collecte. Les sources non autorisées restent refusées par le collecteur.
- **Opt-in global obligatoire** : `OIP_IOC_EXTRACTION_ENABLED=yes` pour le processus de collecte ; par défaut ou pour une valeur inconnue, **aucun candidat n'est créé**. L'ajout de cette variable ne déclenche ni collecte ni planification : les verrous Tor et scheduler restent indépendants.
- Entrées acceptées uniquement dans des champs explicitement étiquetés sur la même ligne : `domain:`, `hostname:`, `ip:`, `ipv4:`, `ipv6:`, `sha256:` ou `sha-256:`. Les URI, URL, noms `.onion`, réseaux privés, adresses non globales, hôtes locaux et valeurs non valides sont exclus.
- Jusqu'à **24 mentions distinctes par observation** sur les 100 000 premiers caractères de texte déjà limité par l'extracteur. Valeurs canonisées (domaines ASCII en minuscules, IP compressées, SHA-256 hexadécimaux) et dédupliquées par observation/type/valeur.
- Stockage minimal : type, valeur canonique, identifiants de la source et de l'observation, score heuristique (50), codes de règle et dates. **Aucun extrait brut**, aucune donnée de connexion, aucun contenu HTML ni lien de preuve fourni au réseau.
- **Quarantaine des contenus sensibles** : aucun candidat IOC ne peut être conservé pour une observation classée `SUSPECTED_CHILD_EXPLOITATION`. Les protections des observations et les contrôles des baux M2 restent inchangés.
- Les nouvelles valeurs IOC, même publiques, peuvent révéler des données contextuelles sensibles. L'interface et les endpoints sont réservés aux rôles **ANALYST/ADMIN**. La rediffusion et l'export sont absents de M5-B.

Les mentions ne constituent ni preuve d'activité malveillante, ni attribution, ni constat d'incident. Le score de 50 mesure la force d'une extraction syntaxique et ne doit pas être présenté comme une probabilité.

## API

Les trois endpoints sont authentifiés et requièrent au minimum le rôle `ANALYST` :

| Méthode | Endpoint | Usage |
|---|---|---|
| `GET` | `/api/v1/cti/ioc-candidates` | Liste paginée et filtrée par source, observation, type et état de revue ; `limit` ≤ 100, `offset` ≤ 10 000. |
| `POST` | `/api/v1/cti/ioc-candidates/{uuid}/review` | Décision `ACCEPTED` ou `REJECTED` à usage unique. Motif de revue **codifié**, priorité analyste distincte de la confiance. |
| `GET` | `/api/v1/cti/ioc-correlations` | Cooccurrences agrégées **uniquement après acceptation** des mentions, sans interprétation de malveillance. |

Motifs de revue : `PUBLIC_REFERENCE_CONFIRMED` pour une acceptation, ou `NON_INDICATOR`, `MISPARSED`, `OUT_OF_SCOPE` pour un rejet. Une entrée rejetée n'est pas supprimée ; elle reste traçable mais exclue des corrélations. L'audit ne contient ni valeur IOC ni texte libre.

## Vérification hors production

Dans un environnement de développement Linux, avec Python 3.12 et les dépendances backend :

```bash
python -m pytest -q backend/tests/test_m5b_ioc_candidates.py backend/tests/test_m5b_migration.py
python -m pytest -q backend/tests/test_m4b_retention.py
python scripts/ci-index-audit.py
```

La migration SQLite est rejouée sur une base de test jetable. La recette PostgreSQL 17 existante (`backend/tests/test_m4b_postgres17.py`) vérifie désormais la création des index M5-B et l'insertion d'une mention synthétique. **Elle ne doit être lancée que sur la base de test vide `oip_m4b_test` en loopback**, avec `OIP_M4B_TEST_DSN`, jamais sur la base OVH. La commande de montée de version est une étape de recette de laboratoire, pas une commande de production.

## Rollback et points à vérifier

- Revenir au code M5-A sans rétrograder PostgreSQL si `0014` a été appliquée : le code précédent ne connaît pas `ioc_candidates`, mais ne la supprime pas.
- La commande Alembic `downgrade 0013_indicator_triage` **supprime définitivement les candidats et leur revue** : à réserver à une base jetable après confirmation explicite.
- Pas de `docker compose down -v`, pas de nettoyage automatique des données, pas de relance non autorisée de Tor/worker ou du scheduler.
- Recette nécessaire : PostgreSQL 17 réel, contraintes uniques sous concurrence, contention des index, RBAC par jetons nominatifs, contrôle des journaux, reprise depuis le dump local et plan d'annulation des migrations.
- Les valeurs extraites sont des *mentions documentaires* ; les sources Onion restent sur liste blanche et aucune valeur découverte n'est transformée en cible de collecte.
