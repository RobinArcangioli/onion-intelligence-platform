# M7-C1 — PostgreSQL 17 réel, concurrence et feuille de route MFA/OIDC

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 retient le jeton API individuel pour l’administration et
> une vitrine visiteur en lecture seule. Leur mise en œuvre est décrite dans
> l’état de référence. Ce guide n’autorise aucune action OVH.

## Statut et périmètre

Le **développement de la recette** est terminé, mais ses scénarios PostgreSQL ne
sont **pas validés** tant qu'un job CI n'a pas exécuté les quatre tests avec un
vrai serveur PostgreSQL 17. Aucun changement de schéma n'est introduit.

OIP reste accessible via **tunnel SSH**, sans exposition de l'UI au réseau public.
Aucune permission réseau Tor et aucun déploiement automatique n'est ajoutée.

## Recette obligatoire avant promotion sur OVH

Le job CI `postgres17-m7c` crée un serveur PostgreSQL 17 **jetable** et une base
nommée strictement `oip_m7c_test`. La connexion est acceptée seulement avec
le pilote `postgresql+psycopg`, l'utilisateur `oip_test`, un mot de passe non vide,
le port PostgreSQL standard et un hôte de boucle locale. Le schéma doit être
**entièrement vide**. Ce test refuse les DSN de production et ne se connecte
jamais à OVH.

Sur cette base, le test :

1. applique les migrations Alembic du début jusqu'à `0017_case_notification_drafts` ;
2. vérifie le schéma, revient de `0017` à `0016`, puis remet `0017` ;
3. tente de désactiver simultanément les deux derniers comptes ADMIN ;
4. tente d'émettre simultanément deux jetons lorsqu'un compte en possède déjà quatre ;
5. tente deux mises à jour d'une même version de dossier et vérifie qu'une seule réussit.

La concurrence repose sur deux connexions/transations réellement distinctes.
Ces scénarios utilisent des données synthétiques ; la collecte Onion est absente.
Une réussite **ne démontre pas** à elle seule la capacité sous forte charge ni
l'absence de toutes les interleavings possibles. Des répétitions et des tests
de charge spécifiques restent nécessaires.

### Exécution manuelle sur une base jetable

La configuration doit nommer exactement `oip_m7c_test` :

```bash
# Variable PG_LOCAL_TEST_DSN préalablement définie dans un secret local (jamais committé).
OIP_M7C_TEST_DSN="$PG_LOCAL_TEST_DSN" python -m pytest -q backend/tests/test_m7c_postgres17.py backend/tests/test_m7c_safety.py
```

Ne pas lancer cette commande sur `vps-ovh`. Les tests changent le schéma de
la base jetable et les rejouent, mais ne savent pas restaurer la production.

### Critères GO/NO-GO

- **GO recette technique** : les migrations jusqu'à `0017` et le retour arrière
  passent sur PostgreSQL 17, les conflits sont correctement arbitrés, les tests
  RBAC et de validation de configuration restent verts, les résultats CI sont conservés.
- **NO-GO production** : tant que l'ensemble des sauvegardes pré-migration,
  de la restauration testée, du plan de rollback et de la conformité Tor n'est
  pas validé. La sauvegarde automatisée reste reportée selon décision du propriétaire.
- Les changements de rôles ou d'accès doivent rester audités ; aucune donnée
  sensible n'est incluse dans les traces de la CI.

## M7-C2 — Décision d'architecture pour MFA/OIDC (non implémenté)

Les jetons API actuels sont des **secrets porteurs** : ils ne constituent pas
une authentification multifactorielle. Leur inventaire, durée de vie, rotation
et révocation ne remplacent pas un second facteur.

Pour un usage privé multi-opérateur, privilégier un **fournisseur d'identité
OIDC** avec MFA/WebAuthn imposée et une architecture d'accès privé distincte
(SSH/VPN ou passerelle à identité). Les protections requises avant toute
implémentation comprennent :

- découverte OIDC et validation stricte de `iss`, `aud`, `exp`, `nonce`, `state`,
  `at_hash` si applicable, algorithmes explicitement autorisés et rotation JWKS ;
- Authorization Code + PKCE pour l'interface navigateur, cookies de session
  `HttpOnly`, `Secure`, `SameSite` adaptés au flux et protection CSRF ;
- correspondance explicite des utilisateurs et rôles, aucun privilège ADMIN
  créé automatiquement depuis un simple claim non administré ;
- déconnexion, désactivation, expiration et révocation de session vérifiables ;
- séparation des accès machine à machine et humains, journalisation expurgée ;
- scénario de panne IdP **fail closed** sans ouvrir de contournement par un en-tête
  de proxy non authentifié ;
- validation d'une récupération administrateur hors bande avant changement
  d'authentification pour ne pas verrouiller tous les comptes.

**À ne pas faire** : accepter une identité à partir de `X-User`/`X-Role` sur une
route publique, considérer la protection du tunnel SSH comme la MFA de l'application,
ou activer des comptes OIDC sans stratégie de migration des comptes locaux.

### Étape suivante

Une fois le fournisseur d'identité et le scénario de connexion choisis par le
propriétaire : concevoir des essais négatifs des jetons OIDC, ajouter une
configuration désactivée par défaut, puis introduire un pilote de connexion sur
un environnement de recette isolé. Aucune authentification OIDC n'est livrée
dans M7-C1 et il ne faut pas présenter ces documents comme un MFA opérationnel.

## M7-C1.1 — lanceur reproductible sur une machine de recette distincte

Une nouvelle procédure permet d'exécuter réellement la recette sur **un poste
Linux distinct de la production**, disposant de Docker, Python 3.12/3.13 et des
dépendances `backend[dev]`. Ce script n'a **pas été exécuté sur PostgreSQL** dans
l'environnement de fabrication du paquet : Docker/serveur PostgreSQL 17 n'y sont
pas disponibles. La vérification réelle reste donc ouverte.

Vérifier les prérequis, puis **uniquement sur une machine de test jetable** :

```bash
# Jamais sur vps-ovh. Jamais dans /opt/oip.
python3 -m pip install -e './backend[dev]'
OIP_CONFIRM_DISPOSABLE_PG17=yes bash scripts/run-m7c-postgres17.sh
```

Le lanceur refuse toute exécution sans approbation explicite, en présence des
variables de connexion `OIP_DATABASE_URL` ou `OIP_M7C_TEST_DSN`, ou lorsqu'il
reconnaît les chemins du serveur de production. Il crée un unique conteneur
`postgres:17-alpine` avec données en mémoire temporaire (`tmpfs`), un mot de
passe aléatoire réservé au test et un port publié uniquement sur
`127.0.0.1:15432`. Il n'utilise aucun volume de production et arrête son
conteneur à la sortie, y compris lors d'un échec. Les variables de contexte
Docker distant (`DOCKER_HOST`/`DOCKER_CONTEXT`) et les contextes non locaux
sont explicitement refusés.

**Important :** Docker doit être configuré pour respecter la liaison aux
interfaces de boucle locale. Exécuter ce test uniquement sur un environnement
de développement dont l'accès réseau est contrôlé. L'image PostgreSQL devra
être obtenue depuis une source de confiance et idéalement fixée par digest
avant automatisation sur un poste sensible.

Les tests refuseront toute base préexistante ou autre que `oip_m7c_test`.
Pendant la CI, `OIP_M7C_REQUIRE_DATABASE=1` et
`OIP_M4B_REQUIRE_DATABASE=1` sont désormais obligatoires pour éviter qu'une
absence accidentelle de base soit considérée comme une exécution réussie.

**Critère d'acceptation restant :** obtenir la sortie d'un passage réel du
script ou d'un job CI PostgreSQL 17, inspecter les éventuels échecs de
concurrence, puis revalider jusqu'à zéro test PostgreSQL ignoré dans la recette.
Aucune des protections ci-dessus ne constitue une autorisation de toucher à
la base OVH existante.
