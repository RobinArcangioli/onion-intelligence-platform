# Provenance, périmètre et audit de la passation

Préparation : 5 novembre 2026 (Europe/Paris).

## Base exacte

Dépôt public vérifié par le connecteur GitHub :
`RobinArcangioli/onion-intelligence-platform`. La seule branche distante au
début de l’inspection était `main`, au commit
`ff7e469fb6f991ee6f69e76754a65abf64d335f8`. Ses neuf tags distants correspondent
aux objets locaux contrôlés. L’historique accessible comprend 11 commits.

Une copie isolée de l’historique a été utilisée. Les répertoires locaux de
travail, leurs changements non commités, leurs branches et leurs tags sont
préservés. Le nouveau commit descend directement de ce `main` ; aucun
force-push, remplacement de racine ou déplacement des anciennes références
n’est prévu.

Source du code : paquet local `OIP-M7C1-1.zip`, SHA-256 :

```text
0e841e4a54157602c7ab2e03dfa0fffb9d38f7385c8e84009edae9f4b4c2de96
```

Cette empreinte correspond au plan local de mise à niveau M7-C1.1 daté du
25 octobre 2026. Le paquet comporte 240 fichiers, dont un manifeste de
239 fichiers ; celui-ci a été vérifié avant toute publication. Aucun chemin
absolu, traversée `..` ou lien symbolique n’a été trouvé dans l’archive.
Les octets des 240 fichiers sont conservés tels quels. Les permissions
exécutables des scripts déjà suivis et des scripts shell sont préservées ou
rétablies pour l’usage Git. Douze fichiers vides hérités de fragments de
sorties terminal ont été retirés du nouvel arbre ; ils restent dans
l’historique existant.

Le prompt `HANDOFF_CODEX.md` et les documents de `docs/handoff/` sont des
ajouts de passation. Ils ne font pas partie du manifeste original, conservé
pour permettre la comparaison au paquet source. L’index Git et son arbre
complet sont audités séparément avant publication. Les copies locales et
archives M7-C2/C3/C4, les sauvegardes, les exports et configurations de test
OIDC ne sont pas inclus dans cette livraison.

## Audit avant publication

- Vérification des références publiques GitHub et de leur correspondance
  avec les objets locaux : branche `main` et neuf tags.
- Audit historique OIP : 11 commits, 284 blobs accessibles, aucun grand blob
  ignoré, aucun secret reconnu ni chemin privé détecté.
- Gitleaks sur toutes les références locales et leur historique : zéro
  détection. Gitleaks sur le paquet extrait avant ajout de dépendances :
  zéro détection.
- Revue des occurrences d’adresses, identifiants et mots de passe dans le
  paquet : exemples de documentation, adresses loopback, sondes réseau fixes
  et données synthétiques de tests. Les identifiants de CI sont des fixtures
  dédiées, pas des secrets opérationnels. Les URL Onion des tests sont
  synthétiques et ne sont pas visitées.
- Les anciens documents numérotés restent accessibles dans les commits
  historiques. L’option existante `--allow-historical-notes` autorise leur
  conservation ; elle n’exempte aucun secret ni chemin privé. Ce choix suit
  la demande explicite de préserver l’historique. Aucun contournement d’une
  alerte de secret n’est autorisé.
- Huit objets de tags annotés contrôlés avec les règles de secrets OIP :
  aucune détection. Audit final de l’index : 243 fichiers, aucune alerte
  bloquante ; Gitleaks sur les changements indexés : zéro détection.
- Les preuves OVH publiées sont des synthèses : ni sortie brute contenant
  le nom du serveur, ni adresse de source, ni identifiant réel de job, ni
  `.env`, clé privée, jeton, dump, export ou contenu collecté.

Les scans sont heuristiques ; zéro détection ne prouve pas l’absence absolue
de secret. Ils ne constituent ni audit de toutes les vulnérabilités du code,
ni certification de l’isolation réseau, ni preuve de rotation d’anciens
identifiants. Aucun matériel sensible n’a été reconnu dans le périmètre
public contrôlé ; une découverte ultérieure doit suspendre la publication
et faire l’objet d’un traitement explicite avec le propriétaire.

## Contrôles locaux exécutés sur M7-C1.1

- Manifeste original : `PASS`, 239 fichiers.
- Backend : 340 réussites, cinq tests ignorés faute de base PostgreSQL 17
  temporaire dédiée et un avertissement de dépréciation du client de test
  Starlette/httpx. La première tentative était bloquée dans le client ASGI
  sous les restrictions locales ; la relance avec permissions locales
  élargies a terminé en 57,50 secondes, sans accès à OVH.
  Dépendances Python locales préexistantes utilisées, sans installation.
- Tests frontend : trois suites, trois réussites.
- Construction frontend (TypeScript et Vite) : réussie avec les dépendances
  locales préexistantes copiées dans l’environnement temporaire ; aucune
  installation réseau. Node 18.19.1 utilisé localement, tandis que la CI
  fournie demande Node 24.
- Contrôles de politique OVH : 23 tests exécutés, 22 réussites et un test
  ignoré car Nginx n’est pas installé. Aucun appel au VPS.
- Syntaxe des scripts shell : réussie.

Les essais PostgreSQL 17, les scénarios Playwright, les scans de dépendances
en ligne et la recette réseau réelle ne sont pas revendiqués comme exécutés
par cette livraison. La CI incluse dans le paquet prévoit des bases
PostgreSQL 17 temporaires ; sa présence ne préjuge pas de son résultat.

Voir `HANDOFF_CODEX.md` pour la reprise et `OVH_STATE.md` pour le dernier état
opérationnel attesté, distinct de ces vérifications locales.
