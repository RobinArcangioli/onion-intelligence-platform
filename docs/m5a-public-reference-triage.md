# M5-A — Références CVE publiques : revue, provenance et corrélations

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 prévoit un admin connecté par mot de passe et une vitrine
> visiteur limitée ; ce modèle n’est pas encore implémenté. Ce guide
> n’autorise aucune action OVH.

Statut : **développement hors production**, après M4-B (`5898c77`).

## But et portée

Ce lot **ne collecte rien** et **n'importe aucun flux externe**. Il utilise uniquement les
références `PUBLIC_CVE_REFERENCE` déjà extraites lors d'une collecte explicitement
autorisée et les identifiants d'observation enregistrés. Il ne stocke pas de texte
intégral, d'IP, de domaine, de hash, d'identifiants personnels, de données volées
ni de nouveaux extraits. La détection d'une CVE est une **citation documentaire**, pas
une preuve de vulnérabilité active ni une validation officielle de la référence.

Une normalisation stricte accepte uniquement `CVE-20YY-NNNN` à
`CVE-20YY-NNNNNNNN` (lettres insensibles à la casse), sans espaces, URL ou suffixe ;
elles sont renvoyées en majuscules sans modifier les zéros significatifs.

## API

Toutes les routes nécessitent un jeton nommé ou le mécanisme de compatibilité
explicitement autorisé par l'instance :

- `GET /api/v1/cti/public-references?reference=cve-2025-12345&limit=50&offset=0` :
  agrégats paginés. `source_count` = nombre de sources distinctes ; `mentions` =
  nombre de résultats non rejetés ; `reviewed_mentions` = mentions examinées et
  acceptées, **pas** validation de la véracité de la CVE ou d'une exploitation.
  Maximum : 100 résultats, offset ≤ 10 000.
- `GET /api/v1/cti/public-references/CVE-2025-12345/evidence?limit=50` :
  indicateurs et identifiants de source/observation horodatés, codes de règles et
  confiance. Pas de corps de page ni de phrase extraite. Maximum : 100 résultats.
- `POST /api/v1/cti/indicators/{uuid}/review` (ANALYST ou ADMIN uniquement) :
  corps `{ "decision": "ACCEPTED", "analyst_priority": "LOW", "reason":
  "Reference relevant to authorized case" }`. Le motif est limité à 10–100
  caractères ASCII imprimables, pour minimiser le risque d'enregistrer des données
  sensibles ; **ne jamais y placer de secrets, de verbatim de pages ou de PII**.
  L'action est atomique, unique et auditée. `REJECTED` impose
  `analyst_priority="UNASSESSED"`.

La revue est limitée aux **références CVE publiques**. Les indicateurs de type
`DATA_LEAK_CLAIM`, `RANSOMWARE_CLAIM` ou `ACCESS_SALE_CLAIM` restent non confirmés
et ne peuvent pas être « acceptés » via cette API.

`confidence` reste un score heuristique d'indice documentaire (0–100) issu des
règles, non modifiable par la revue. `analyst_priority` = priorisation humaine
du traitement (`UNASSESSED`, `LOW`, `MEDIUM`, `HIGH`), **pas** CVSS, sévérité,
probabilité de compromission ou valeur de vérité. L'acceptation signifie seulement
que **la présence de la référence dans l'observation a été vérifiée**.

Les faux positifs `REJECTED` disparaissent des agrégats et de la liste de
preuves courantes, mais l'indicateur et sa piste d'audit sont conservés.
Les sources différentes ne sont pas nécessairement indépendantes : des pages
peuvent reprendre une même publication. La corrélation indique une
**cooccurrence**, jamais une corroboration de l'allégation.

## Schéma / déploiement

Migration additive `0013_indicator_triage`, sur `threat_indicators` :
`review_status`, `analyst_priority`, `review_reason`, `reviewed_at` et index
`ix_indicator_reference_review`. Toutes les lignes existantes sont initialisées
`PENDING`/`UNASSESSED` (pas de revue implicite).

Cette migration **ne doit pas être appliquée sur `vps-ovh` à cette étape**. Le VPS
est resté avec M1-A et Tor désactivé ; aucune sauvegarde automatisée hors site
n'est encore validée. Conditions avant activation : restauration hors VPS
vérifiée et récente, répétition complète des migrations `0009` à `0013` sur une
copie PostgreSQL 17 jetable, tests multi-workers M2, contrôle réseau OVH, puis
GO distinct. Une restauration préalable couvre aussi le downgrade, qui fait
perdre les champs de revue si utilisé ; ne pas l'exécuter en production.

Commandes **pour poste de développement / base jetable seulement** :

```bash
cd backend
python -m pytest -q tests/test_m5a_public_cti.py tests/test_m5a_migration.py
python -m alembic heads
# Ne lancer un upgrade que sur une DB explicitement de TEST dédiée :
# OIP_DATABASE_URL=sqlite+pysqlite:////tmp/oip-m5a-test.db python -m alembic upgrade head
```

Le test PostgreSQL 17 facultatif est appelé par `test_m4b_postgres17.py` sur une
base vide nommée **exactement** `oip_m4b_test`, en loopback ; il couvre la création
de l'index M5-A. Sans serveur PostgreSQL 17 local ou CI accessible, il est
**ignoré**, pas validé.

## Découpage ultérieur

M5-B pourra traiter les IOC de nature différente (hashes/domaines/IP) **après**
définition explicite des règles de confidentialité, de rétention, du périmètre
de sources et des restrictions d'export. Ne pas ouvrir la collecte ou les exports
STIX/TAXII/MISP par défaut. Ajouter une revue humaine, une vraie évaluation
séparée de confiance/sévérité et des faux positifs mesurés avant diffusion.
