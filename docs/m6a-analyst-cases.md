# M6-A — Dossiers d'analyse liés aux alertes (développement uniquement)

**Statut : GO code/test SQLite ; NO-GO production OVH.** Le jalon ajoute la
migration additive `0015_analyst_cases` et une interface « Dossiers » ; ne pas
lancer `alembic upgrade head` sur le VPS en fonctionnement. Avant une
migration réelle : restauration externe vérifiée, répétition PostgreSQL 17,
revue des verrouillages et plan de retour arrière.

## Périmètre

Un utilisateur `ANALYST` ou `ADMIN` peut créer **un dossier par alerte
existante**, voir la liste filtrée et le détail, assigner à un opérateur nommé
actif (`ANALYST`/`ADMIN`), désassigner, examiner, escalader, reprendre puis
clore. Les `VIEWER` ne lisent pas les dossiers et ne déclenchent aucune
mutation. La création et chaque décision sont enregistrées en événements
append-only (`analyst_case_events`) et dans l'audit existant. L'API ne reçoit
aucun corps de page ni note libre. Le motif de clôture est un **code fermé**.

Machine d'états autorisée :

```
OPEN --START_REVIEW--> IN_REVIEW --ESCALATE--> ESCALATED
                         ^                 |
                         +--RETURN_REVIEW--+
IN_REVIEW ou ESCALATED --CLOSE + motif--> CLOSED (terminal)
```

`ASSIGN` et `UNASSIGN` ne modifient pas le statut et sont interdits en `CLOSED`.
Les cas ne sont **pas** des incidents avérés ; les alertes, leur sévérité et
leurs données CTI ne sont pas modifiées par la création/clôture d'un dossier.
Il n'existe ni envoi d'e-mail, ni webhook, ni nouvel accès Internet.

## API (jeton nominatif dans `X-API-Key`)

| Méthode/route | Rôle | Résultat |
|---|---|---|
| `POST /api/v1/cases` | ANALYST+ | `201`, corps `{ "alert_id": "UUID" }` ; `409` si dossier existant |
| `GET /api/v1/cases?status=OPEN&limit=50&offset=0` | ANALYST+ | pagination, filtres `status`, `alert_id`, `assignee_username` |
| `GET /api/v1/cases/{id}` | ANALYST+ | dossier avec responsable |
| `GET /api/v1/cases/{id}/events` | ANALYST+ | événements paginés (dernier d'abord) |
| `GET /api/v1/cases/assignees` | ANALYST+ | opérateurs nommés, actifs et autorisés (max 100) |
| `PATCH /api/v1/cases/{id}` | ANALYST+ | action structurée et version attendue |

Commande illustrée (identifiants fictifs) :

```json
{"action":"START_REVIEW","expected_version":1}
```

`ASSIGN` exige `assignee_username` ; `CLOSE` exige `closure_code` égal à
`DOCUMENTED`, `NOT_RELEVANT` ou `DUPLICATE`. Les autres actions les refusent.
La commande compare la version en base dans un `UPDATE` atomique et renvoie
`409` si elle a changé : recharger le dossier et reconsidérer la décision.
Chaque version correspond à un événement, écrit dans la même transaction.
Les actions concurrentes sur SQLite sont testées séquentiellement ; la
concurrence réelle à plusieurs API PostgreSQL reste **non vérifiée**.

## Rétention, sécurité et limites

- Pas de note arbitraire, de copie du texte de page, de pièce jointe ou d'IOC
  supplémentaire. Les événements conservent acteur, action, horodatage, code
  de clôture et identifiant du responsable choisi.
- Les journaux `AuditLog` stockent uniquement des codes et la version du
  dossier, sans texte libre ni jeton.
- La suppression d'un `Operator` ou d'une `Alert` référencés doit être gérée
  comme une migration de données : elle n'est pas offerte par l'API M6-A.
- Les événements ne sont pas immuables cryptographiquement ; l'accès direct
  à PostgreSQL par un administrateur peut toujours les modifier. Il ne faut
  pas qualifier cet audit de « non falsifiable ».
- L'interface propose les 100 dernières alertes pour l'ouverture de dossier ;
  l'API permet de créer depuis un identifiant d'alerte historique connu.
- La liste des responsables est bornée à 100 entrées. Prévoir recherche
  paginée avant une mise à l'échelle de l'équipe.

## Validation hors production

```bash
cd backend
python -m pytest -q tests/test_m6a_cases.py tests/test_m6a_migration.py
cd ../frontend
npm run test:unit
npm run build
```

La répétition de migration emploie uniquement une SQLite temporaire. Le
`downgrade` de `0015` détruit **les dossiers et événements** ; il ne doit
jamais être utilisé comme rollback de données en production.

## Retour arrière pour une future livraison

Avant activation, conserver une sauvegarde externe testée, puis répéter les
migrations sur une copie PostgreSQL 17. Une fois la migration exécutée et des
dossiers enregistrés, privilégier le retour à la version précédente de
l'application **en conservant les nouvelles tables** : l'ancienne version ne
les lit pas. N'exécuter le downgrade destructif que sur une base de test
jetable. Avant re-promotion, vérifier schéma et intégrité des enregistrements.

## Hors périmètre M6-A

Notes libres soumises à politique de rétention, notifications email/webhook,
SLA, files d'escalade externes, fusion de dossiers, dossiers multi-alertes,
tests de charge multi-opérateurs et revue UI Playwright. Ces éléments
nécessitent des choix d'accès, de minimisation et des tests supplémentaires.
