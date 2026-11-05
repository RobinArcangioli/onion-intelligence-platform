# OIP — Roadmap et décisions

Révision : 2026-11-05, Europe/Paris. Référence factuelle associée :
[État de référence](ETAT_DE_REFERENCE.md), base `44101c593d19f0ee8122bf3d7d10607fde541a12`.
Ce document est l'unique suivi actif des travaux et arbitrages. Les anciens
backlogs/« prochaines étapes » décrivent leur époque, pas un engagement actuel.

## 1. Objectif arrêté pour la reprise

Produire une base documentaire et technique stable, puis un MVP centré sur la
**collecte manuelle permanente et supervisée**. « Permanente » signifie que le
worker peut rester disponible pour traiter les demandes humaines ; cela ne
signifie ni collecte récurrente autonome ni navigation automatique. Le scheduler
reste désactivé. Un **administrateur conserve la connexion actuelle par jeton API individuel** ; un
**visiteur accède à une vitrine des dernières veilles**, sans accès aux fonctions
ni aux informations sensibles. Les sauvegardes automatiques et leur restauration
deviennent des prérequis d’exploitation durable.

Ces choix viennent des réponses explicites du propriétaire du 5 novembre 2026.
Ils ne constituent pas une autorisation de connexion ou de déploiement OVH.
La stabilisation présente centralise les références et nettoie leur navigation ;
la séparation de l’accès visiteur, la vitrine et la préparation du mode permanent
sont les incréments suivants, avec revue de leur périmètre ci-dessous.

## 2. Registre des décisions

| ID | Décision | Statut / provenance | Conséquence |
|---|---|---|---|
| D01 | Base unique M7-C1.1 au commit `44101c5…` | Acté, demande initiale | Comparer toute autre archive avant reprise ; ne pas importer M7-C2/C3/C4 implicitement |
| D02 | Conserver historique, tags, migrations et tests utiles | Acté, passation et objectif de références stables | Aucun nouveau dépôt racine, force-push ni réécriture ; nettoyage documentaire traçable |
| D03 | Deux références centrales : état et roadmap | Acté, demande initiale | README et passation y renvoient ; guides techniques subordonnés pour le statut |
| D04 | Collecte manuelle permanente supervisée prioritaire | Acté, réponse du propriétaire 2026-11-05 | Worker disponible en continu, sources explicitement autorisées, concurrence bornée, stop ; scheduler désactivé |
| D05 | Retirer toute authentification applicative du MVP | REMPLACÉ par D10, précision ultérieure du propriétaire le 2026-11-05 | Ne plus utiliser cette première formulation comme cible ; l’administration reste authentifiée |
| D06 | Remettre les sauvegardes automatiques dans les prérequis d'exploitation durable | Acté, réponse du propriétaire 2026-11-05 | Conception, restauration réelle et supervision avant exploitation durable ; pas d'activation distante implicite |
| D07 | Aucun accès OVH, déploiement ou activation de collecte pendant cette reprise | Acté, périmètre de passation | Préparer et tester localement ; intervention distante sur instruction explicite ultérieure |
| D08 | Sources autorisées, minimisation, aucune navigation automatique, pas de retry automatique | Contrats existants maintenus | Simplifier les accès ne retire pas les contrôles de sources, limites et transitions |
| D09 | Conserver le profil réseau privé existant pendant la stabilisation | Maintien de l’existant ; cible web commune précisée dans D12 | La conception de la vitrine ne modifie aucun port ni accès distant pendant cette étape |
| D10 | Conserver le jeton API individuel existant comme seule authentification ; visiteur limité à la vitrine | Acté, clarification finale du propriétaire 2026-11-05 ; remplace D05 et l’interprétation « nouveau mot de passe » | Connexion et gouvernance des jetons conservées ; aucune interface de choix/modification de mot de passe, aucun remplacement par sessions cookie ; OIDC/MFA hors MVP |
| D11 | Métadonnées publiques par défaut ET rapports publiés explicitement par l’admin | Acté, réponse du propriétaire 2026-11-05 | Deux circuits distincts : données publiques automatiques bornées par D13 ; publication volontaire de rapports, aucun accès implicite aux autres rapports |
| D12 | Même adresse web que l’admin, petit lien latéral « accès visiteur », sans connexion visiteur | Acté, réponse du propriétaire 2026-11-05 | Vue restreinte de l’interface et API de lecture publique ; connexion par jeton API individuel réservée aux accès internes autorisés ; exposition effective à préparer/tester avant déploiement |
| D13 | Champs publics par défaut : date, statut, volumes et noms des sources ; sans adresse Onion | Acté, réponse du propriétaire 2026-11-05 | Liste de champs publique explicite, sans exposition des objets internes complets ; audit des noms de sources et des réponses avant mise en ligne |

La connexion existante par jeton API individuel est conforme au choix retenu :
elle est **conservée**, avec les rôles, expiration, révocation et gouvernance des
jetons déjà livrés. Le propriétaire utilisait « mot de passe » pour désigner ce
jeton ; aucune nouvelle authentification, session cookie ou interface de gestion
de mot de passe n’est demandée. Le rôle `VIEWER` actuel ne constitue pas la vitrine
anonyme : ses droits doivent être comparés à D11/D13 sans les élargir implicitement.
Les contrôles serveur des accès internes restent en place. Une décision actée est
modifiée uniquement par une nouvelle décision explicite et datée.

## 3. Contrat documentaire et règle de livraison

L'état décrit les capacités et leurs limites, avec preuves datées et périmètre
précis. Cette roadmap contient les tâches et les choix. Les guides détaillent
les procédures ; les synthèses `docs/handoff/` restent des preuves historiques.
Un lot n'est « terminé » qu'avec un diff borné, des contrôles appropriés, les
résultats et non-exécutions explicites, et ces deux références à jour.

Pour une version destinée à être une référence stable : commit exact, manifeste
vérifié, CI entièrement verte, aucun test indispensable silencieusement ignoré,
revue des écarts documentaires et décisions bloquantes résolues. Une référence
de code ne suffit pas à déclarer l'exploitation qualifiée. Une vérification de
manifeste ne doit pas être désactivée pour absorber un changement non documenté.

Statuts autorisés des tâches : À FAIRE / EN COURS / VALIDÉ / BLOQUÉ PAR DÉCISION.
Les tailles sont relatives (S : incrément court, M : plusieurs incréments, L :
chantier transversal) ; aucune date de livraison n'est promise sans exécution.
Responsable d'implémentation proposé : Codex, en local ; arbitrages et GO distants :
propriétaire. Les délais d'infrastructure dépendent des accès futurs autorisés.

## 4. Stabilisation avant évolution fonctionnelle

| ID / priorité / taille | Travail et dépendances | Critère de sortie vérifiable | État |
|---|---|---|---|
| S01 / P0 / S | Identifier la copie, lire passation et guides, comparer à `main`, inspecter jobs et logs CI | SHA exact, état propre initial, provenance et limites inscrits dans l'état ; distinction CI/local/OVH | VALIDÉ pour l'inspection initiale |
| S02 / P0 / S | Centraliser les deux références, remplacer le README chronologique, baliser les statuts hérités, conserver le manifeste source | Deux entrées principales ; aucun guide balisé pris pour photo actuelle ; liens et manifeste courant vérifiés | VALIDÉ pour la livraison locale documentaire |
| S03 / P0 / S | Corriger uniquement l'isolation du test syntaxique Nginx (`test_m7a_nginx_policy.py`) ; après S01 | PID et chemins requis sous répertoire temporaire ; `nginx -t` non-root réussit ; 23 politiques passent avec Nginx présent, aucun skip ; config applicative inchangée | VALIDÉ localement, Nginx 1.24.0, 23/23 |
| S04 / P0 / S | Rejouer les quatre jobs sur le commit de stabilisation ; après S02/S03 | Backend et politiques verts, frontend 14 tests + build verts, PG M4-B et M7-C sans skip ; SHA/run consignés, syntaxe shell/compile effectivement exécutée | VALIDÉ : commit `244437b…`, run `42018926671`, quatre jobs verts |
| S05 / P0 / S | Revue des deux références et clôture des décisions de périmètre ; après S02/S04 ; D10–D13 actées | Propriétaire valide périmètre ; commit de référence retenu et CI associée ; `main`/tag éventuel sur instruction explicite | VALIDÉ pour la référence technique de branche ; aucune promotion main/tag |

La correction S03 a été validée localement et par le run `42018926671`.
Le défaut initial était identifié dans le log : `open() /run/nginx.pid failed (13:
Permission denied)` après « syntax is ok ». Ne pas installer le test en root,
le sauter ou supprimer son assertion pour obtenir un faux vert.

S02 ne supprime ni archive de passation, ni migration, ni test de lot, ni branche.
Les anciennes contradictions restent lisibles avec un avertissement de provenance
pour éviter une réécriture spéculative des procédures avant validation technique.
Le script `cleanup-legacy-docs.py` est en dry run par défaut ; son existence n'est
pas une raison de lancer une suppression large.

## 5. Construire le MVP local : ordre de dépendance

### MVP-01 — Conserver les jetons et séparer l’accès visiteur (P1, M)

Dépend de S05 et D10–D13. La connexion admin existe déjà et convient au MVP :
**aucune refonte de l’authentification**. Conserver le formulaire de jeton API,
la transmission `X-API-Key`, le stockage en mémoire React, les rôles et la gestion
locale des jetons. Ne pas ajouter de mot de passe administrateur distinct, de
session cookie, ni d’interface pour choisir/modifier un mot de passe.

Inventorier les API et définir une matrice explicite : visiteur anonyme = seules
métadonnées D13 et versions de rapports publiées selon D11 ; accès internes =
jeton valide et permissions existantes. Créer une frontière de lecture publique
dédiée, sans désactiver globalement `require_api_key` ou les contrôles de rôle.
Préserver les migrations et l’attribution existante des événements d’audit.

**Acceptation :** connexion actuelle inchangée ; jetons invalides, expirés ou
révoqués toujours refusés sur les API internes ; visiteurs sans accès aux sources
internes, observations, IOC, notes, dossiers, exports internes ou champs hors D13 ;
requêtes directes d’API et accès par identifiants devinés également refusés ;
contrôles de source, quotas, stop et conflits 409 conservés. Le moniteur vérifie
la vitrine permise et le refus des API internes sans jeton ; ne pas remplacer
globalement ses attentes 401 par des 200. Aucun nouveau secret ou mécanisme
persistant navigateur n’est introduit.

### MVP-01V — Vitrine des dernières veilles (P1, M)

Dépend de D11–D13 et de la séparation MVP-01. À la même adresse web que
l’administration, proposer un petit lien latéral **« accès visiteur »** qui ouvre
une vue restreinte sans connexion. Définir des réponses API dédiées avec liste
explicite de champs ; ne pas réutiliser les endpoints internes en masquant
simplement quelques champs dans React.

Deux circuits de publication distincts :

1. **Métadonnées automatiques des dernières veilles** : date, statut, volumes et
   noms des sources, sans adresse Onion. Définir précisément le statut affiché,
   les unités des volumes, le tri et les dates ; ne pas transmettre de détails
   d’erreur, d’URL ou d’objets source internes avec ces champs. Les noms étant
   publics, vérifier qu’ils ne contiennent pas d’adresse Onion ni de secret ;
   proposer une règle de libellé public compatible avec ce contrat si nécessaire.
2. **Rapports sur décision admin** : les rapports restent internes tant qu’ils ne
   sont pas publiés explicitement. Prévoir aperçu du contenu public, publication
   d’une version identifiée et dépublication. Le contenu publié doit respecter
   l’interdiction d’exposer les informations sensibles ; ne pas rendre public
   l’export interne complet sans revue. Une modification interne ultérieure ne
   doit pas modifier silencieusement la version déjà publiée. Les règles détaillées
   d’expurgation et le format public seront conçus avant l’implémentation.

**Acceptation :** les quatre catégories de métadonnées D13 sont consultables sans
connexion ; noms autorisés visibles, adresses Onion et champs internes absents ;
rapports non publiés inaccessibles, y compris par URL/API directe ; version publiée
visible et dépublication effective ; toute publication/mutation réservée à l’admin ;
tests avec valeurs synthétiques sentinelles dans les champs sensibles démontrant
leur absence des réponses, erreurs et exports publics. Tester états vide/indisponible,
pagination, passage visiteur/admin et déconnexion ; aucun accès à la collecte
depuis la vitrine. Le réseau et les secrets réels ne sont pas modifiés par cette
conception locale.

### MVP-02 — Qualifier file et scheduler inactif sur PostgreSQL (P1, M)

Dépend de S04, adapté au modèle MVP-01. Développer des essais synthétiques avec
sessions/processus PG17 réellement distincts : admissions simultanées d'une même
source, quotas globaux, claim `SKIP LOCKED`, renouvellement/perte de bail, ancien
worker tentant de finaliser, révocation de source pendant le traitement,
interruption DB et arrêt d'urgence. Vérifier que le profil cible n'active jamais
le scheduler. Utiliser de faux fetchers, aucune destination Onion réelle.

**Acceptation :** un job actif par source, plafonds respectés, aucun résultat
persisté par un bail périmé ou après révocation constatée, aucune relance implicite,
jobs interrompus identifiables/récupérables après arrêt attesté. Scénarios répétés
avec timeouts pour détecter deadlocks ; résultats PG17 datés. La CI M7-C actuelle
n'est pas une preuve de réalisation de cette tâche.

### MVP-03 — Supervision compatible avec un worker permanent (P1, M)

Dépend de MVP-01/02. Introduire un profil explicite distinguant noyau privé sans
collecte et collecte manuelle supervisée. Conserver le refus de Tor/worker dans
le premier. Pour le second, vérifier présence et état des services attendus,
verrous cohérents, âge des jobs en attente et baux, erreurs/circuit, ressources,
ports et indisponibilités DB/Tor. Ne pas faire de sonde externe réelle implicite.
Le prévol `check_compose.py`, qui exige actuellement les verrous à `false`,
doit être adapté à ce profil de façon contrôlée, pas neutralisé globalement.

**Acceptation :** tests du profil privé inchangés dans leur objectif ; profil
manuel sain avec worker attendu et défaillant s'il manque ; scheduler actif ou
service inattendu signalé ; alerte sur incident simulé, sans URL/contenu/secret.
Runbook d'arrêt, diagnostic, réconciliation et reprise testé localement.

### MVP-04 — Sauvegardes automatiques et reprise (P1, M)

Conception parallélisable après S05 ; validation obligatoire avant exploitation
durable. Définir avec le propriétaire la destination hors hôte, le chiffrement,
la détention des clés, la fréquence, la rétention, le RPO et le RTO. Réutiliser
et vérifier `backup-offsite.sh`, `verify-restore.sh`, leurs gardes et unités
systemd au lieu de présumer qu'ils constituent un service déjà opérationnel.
Aucun accès à des secrets ou activation réelle par simple validation documentaire.

**Acceptation :** scénario synthétique complet dump → chiffrement → transfert de
recette → restauration sur base vierge → intégrité applicative ; panne dump ou
transfert ne produit pas de faux marqueur de succès ; retard déclenche l'alerte ;
RPO/RTO mesurés et procédure de récupération de clé validée. Avant exploitation
réelle, restauration effective autorisée et preuve expurgée distincte du test local.

### MVP-05 — Recette navigateur et qualité d'extraction (P1, M)

Dépend de MVP-01/01V/02. Préparer une stack locale sur données entièrement synthétiques,
avec fetcher de test fermé au réseau externe. Tester après connexion admin : ajout d'une
source, autorisation, clic manuel, transitions et observation, erreurs, désactivation
de source, stop et affichage du résultat. Revoir les scénarios Playwright actuels
qui exigent un jeton ou sautent des contrôles faute de source. Ajouter le parcours
visiteur et des tests négatifs contre les API internes. Ne pas transformer
la suite release en collecte réelle.

Créer un corpus synthétique HTML/plain text avec navigation, scripts, encodages,
métadonnées, absence de texte, doublons et dépassement des bornes. Mesurer et
expliquer extraction/hash/longueur et faux positifs CTI, sans extrapoler au pilote
historique ni ajouter d'archivage HTML.

**Acceptation :** parcours MVP sans skip de données manquantes ; erreurs lisibles ;
aucun appel externe ; métadonnées et hash attendus ; contenu brut non persisté ;
aucune découverte suivie automatiquement ; limitations d'extraction documentées.

### MVP-06 — Reproductibilité et contrôles de livraison (P1, M)

Commencer après S04, terminer avant promotion. Décider d'une version Node commune
CI/Docker (24 en CI, 22 dans l'image actuelle) ; figer les dépendances Python
transitives avec un mécanisme de verrouillage reproductible et éprouver le build
depuis zéro. Fixer les images/digests retenus et documenter leur mise à jour.
Ajouter audits de dépendances et scan de secrets appropriés, sans appeler une image
API réelle d'exploitation pour collecter son inventaire de paquets.

**Acceptation :** installation propre reproductible, backend/frontend et images
construits sur la même base définie, inventaire des composants et scans datés ;
échec bloquant pour vulnérabilités dépassant le seuil convenu ou secret reconnu ;
exécuter `bash -n` individuellement sur chaque script (la commande CI actuelle
avec un glob ne vérifiait que le premier script, les suivants devenant arguments ;
corrigé dans le workflow de stabilisation) ;
aucun déploiement automatique ni secret d'exploitation dans la CI.

## 6. Passage ultérieur vers l'exploitation durable

| ID | Dépendances | Travail et critères d'acceptation |
|---|---|---|
| OPS-01 / P1 / M | MVP-01 à 06 et MVP-01V | Plan staging/promote/rollback sur schéma `0017`, restauration préalable, vérification de compatibilité applicative ; distinguer rollback image et restauration DB ; ne pas utiliser un downgrade destructif comme sauvegarde |
| OPS-02 / P1 / M | OPS-01 + instruction d'accès distante explicite | Inventaire actuel OVH expurgé, vérification du périmètre de l'autorisation fournisseur déclaré historiquement, revue IPv4/IPv6/DNS/SOCKS/ports, tests stop/absence de fallback sur l'hôte autorisé ; résultats datés, aucune revendication d'anonymat absolu |
| OPS-03 / P1 / S | OPS-02 + sauvegarde/restauration validées + GO explicite | Pilote de durée convenue, un worker initialement, concurrence réglée et sources de démonstration autorisées ; scheduler inactif ; preuves des transitions, arrêt et reprise ; seuils et incidents suivis |
| OPS-04 / P1 / S | OPS-03 | Recette opérateur, limites connues, SLO modestes mesurés, coûts et runbooks ; deux références actualisées avec SHA/run/date ; validation MVP par le propriétaire |

L'ordre critique est : S01–S05 → MVP-01/02 → MVP-01V/03/05 → OPS-01/02/03/04.
MVP-04 (reprise) et MVP-06 (reproductibilité) avancent en parallèle de conception,
mais doivent être validés avant OPS-01. Aucune étape distante n'est déclenchée par
ce document. Un budget de durée et de ressources du pilote sera convenu avant OPS-03.

## 7. Travaux conditionnels, hors chemin critique MVP

- Planification gouvernée active : seulement si demandée ultérieurement ; qualification
  PG multi-schedulers, quotas, pause/expiration et supervision spécifiques avant GO.
- Notifications sortantes : chantier distinct si demandé ; les brouillons actuels
  restent locaux. Définir canaux, destinataires, secrets, minimisation et gestion
  d'échec avant toute implémentation de transport.
- Rétention/purge : conserver la simulation existante ; demander les durées par
  catégorie, analyser dossiers/notes/brouillons, références JSON et audit, tester
  suppression/restauration sur données synthétiques avant une éventuelle politique.
- Échelle et CTI : charge PG représentative, pagination, qualité et faux positifs,
  règles de lecture des dossiers et éventuels exports sur besoin confirmé. Les
  capacités existantes ne sont pas retirées silencieusement du produit.
- Une éventuelle reprise de travaux M7-C2/C3/C4 exige inventaire et comparaison
  explicites ; les identifiants de ces lots ne prouvent pas leur compatibilité
  avec le modèle MVP conservant les jetons et ajoutant la vitrine limitée.

OIDC/MFA et les fonctions d'équipe fondées sur l'authentification ne sont pas des
prérequis MVP. Les remettre dans le périmètre exigerait une nouvelle décision.

## 8. Clôture de la stabilisation et prochaine action

La stabilisation technique est validée : **S01–S05 terminées pour la branche de
travail**, sans promotion sur `main` ni création de tag. La référence technique est
**`244437baf6d3c8fe8656b50c17a45e09b07a81f6`**, validée par les quatre jobs du
[run 42018926671](https://github.com/RobinArcangioli/onion-intelligence-platform/actions/runs/42018926671).
Les résultats détaillés et leurs limites figurent dans l’état de référence.
Le commit documentaire suivant consigne cette preuve sans modifier l’application.

Les décisions de parcours et de visibilité D10–D13 sont actées. La prochaine
étape fonctionnelle est **MVP-01**, puis **MVP-01V** : conserver la connexion
par jeton existante, séparer les API publiques/internes et ajouter la vitrine
des métadonnées et rapports publiés. Les détails de
conception (unités, libellés et contenu des versions de rapport) seront documentés
dans ces incréments avant mise en service. Aucune activation ou intervention OVH
n’est réalisée par cette stabilisation.
