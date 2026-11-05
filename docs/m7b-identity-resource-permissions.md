# M7-B — Identités et permissions par dossier

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 prévoit un admin connecté par mot de passe et une vitrine
> visiteur limitée ; ce modèle n’est pas encore implémenté. Ce guide
> n’autorise aucune action OVH.

## Objet et périmètre

Ce lot durcit les identités nominatives et les droits d'écriture des dossiers d'analyse, sans migration SQL, collecte réseau ou changement de déploiement. Il **ne fournit pas** de MFA, SSO/OIDC, gestion des sessions web, multi-tenant ni permissions de lecture confidentielles par dossier.

### Règles des dossiers

- Un dossier **non attribué** peut être modifié par un `ANALYST` ou `ADMIN`.
- Un `ANALYST` ne peut s'attribuer **que lui-même** et uniquement un dossier non attribué.
- Sur un dossier attribué, seuls son responsable actif (`ANALYST`/`ADMIN`) et un `ADMIN` peuvent modifier le statut, la priorité, l'assignation ou ajouter une note.
- Un `ADMIN` peut réassigner un dossier et réaliser les modifications autorisées par le workflow.
- Les consultations restent accessibles à tous les `ANALYST`/`ADMIN` selon la politique d'équipe actuelle : cela **n'isole pas** les dossiers les uns des autres.
- Les modifications sont toujours protégées par le numéro de version du dossier. Une réassignation concurrente doit provoquer un conflit (409) plutôt qu'écraser les changements d'un autre analyste.
- Les dossiers clôturés restent non modifiables.
- La clé d'API historique (si explicitement activée) conserve les privilèges `ADMIN` : **désactiver cette clé avant une utilisation multi-opérateur réelle**.

### Gestion locale des opérateurs

Depuis l'environnement autorisé contenant la CLI et la base, exécuter (ne jamais transmettre de jeton en paramètre de commande) :

```bash
python -m app.security.manage_users list
python -m app.security.manage_users create alice --role ANALYST --days 30
python -m app.security.manage_users set-role alice --role VIEWER
python -m app.security.manage_users disable alice
python -m app.security.manage_users enable alice
python -m app.security.manage_users issue alice --days 30
python -m app.security.manage_users revoke UUID_DU_JETON
```

La CLI :

1. refuse la désactivation ou la rétrogradation **du dernier administrateur actif** ;
2. révoque tous les jetons non révoqués lors d'un changement de rôle ou d'une désactivation, et trace le nombre de jetons révoqués ;
3. ne réactive jamais d'anciens jetons après `enable`. Un nouveau jeton doit être émis explicitement avec `issue` ;
4. n'affiche le secret d'un nouveau jeton **qu'au moment de sa création**. La sortie de cette commande est confidentielle ;
5. journalise les changements d'identité sans empreinte ni valeur du jeton.

La protection du dernier administrateur utilise un verrou de lignes `SELECT ... FOR UPDATE` sur PostgreSQL. Les tests SQLite sont utiles pour la logique mais ne démontrent **pas** la sécurité sous forte concurrence sur PostgreSQL. La CLI doit être exécutée par un opérateur disposant déjà d'un accès système très privilégié ; ne pas exposer cette CLI comme API.

### Vérifications et limites

```bash
PYTHONPATH=backend:. pytest -q backend/tests/test_m7b_identity_permissions.py \
  backend/tests/test_m6a_cases.py backend/tests/test_m6b_case_collaboration.py
```

En production OVH, **ne pas appliquer** les nouveaux fichiers avant une revue de migration, un test de restauration hors production et une décision de mise en service spécifique ; le paquet M7-B n'est pas une instruction de déploiement. Le contrôle Tor reste distinct et désactivé.

Tests PostgreSQL 17 multi-processus de rotation, règles de visibilité par ressource, MFA/SSO, alertes sur identités, vérification des tokens expirés et robustesse des journaux d'audit restent à planifier pour M7-C / M8.
