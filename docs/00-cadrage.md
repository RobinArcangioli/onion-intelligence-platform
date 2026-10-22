# 00 — Analyse du cahier des charges et périmètre

## Mission

Construire une plateforme de renseignement documentaire sur des services `.onion`, uniquement pour des sources textuelles accessibles et explicitement autorisées. Décrire des observations et déclarations sans les transformer automatiquement en preuves. Le système ne réalise ni intrusion, ni contournement d'accès, ni transaction, ni téléchargement de médias ou de bases volées.

## Besoins fonctionnels

| Domaine | Comportement attendu | Livraison cible |
|---|---|---|
| Sources | Ajout, état, édition, archivage, import/export, liste d'autorisation | Lots 0–1 |
| Disponibilité | Contrôle borné de disponibilité à travers Tor | Lot 2 |
| Collecte | HTTP textuel sans JS, sans binaire, avec budgets de trafic | Lot 3 |
| Extraction | Titre, description, texte, date, liens, empreinte | Lot 3 |
| Découverte | Extraire les `.onion` v3, dédupliquer, conserver la provenance | Lot 4 |
| Validation | File d'approbation humaine, refus/quarantaine | Lots 1 et 4 |
| Watchlist | Mots-clés, expressions, marques, domaines, CVE | Lot 4 |
| Scores | Pertinence 0–100 et explication des critères | Lot 4 |
| Catégories | Multi-étiquette descriptive, confiance séparée | Lot 4 |
| Indices CTI | Distinguer revendication, rapport non vérifié et élément corroboré | Lot 4 |
| Historique | Page, observation, statut, audit et rétention | Lots 0–4 |
| Alertes | Déduplication et notifications internes | Lot 5 |
| Rapports | Export JSON/CSV, réserves et traçabilité | Lot 5 |
| Dashboard | Vue générale, sources, découvertes, recherche, alertes, rapports | Lot 6 |

## Besoins non fonctionnels

- **Sécurité :** aucune collecte sans autorisation préalable, validation et périmètre strict; fail-closed sur défaillance Tor; aucun accès HTTP direct de secours.
- **Conformité :** minimisation, rétention configurable, procédure de quarantaine et revue humaine, aucune conservation de contenu d'exploitation sexuelle de mineurs.
- **Fiabilité :** limites de taille, de durée, de profondeur, de concurrence; reprises explicites; aucune tâche silencieusement perdue.
- **Traçabilité :** source, page de provenance, date UTC, hash textuel, justification de score, audit des approbations.
- **Évolutivité :** API, moteur de règles, collecte et reporting découplés par modules / contrats clairs.
- **Reproductibilité :** source Git, Docker Compose, migrations versionnées, tests hors ligne, fichiers `.env.example`.
- **Observabilité :** endpoint vivant, endpoint prêt, logs structurés sans secrets, métriques futures.
- **Interface :** dark mode par défaut, vues filtrables, responsive; hors lot initial.

## Décisions pour le MVP

1. Un seul backend FastAPI, un seul PostgreSQL, un frontend séparé à l'étape adéquate; pas de Celery/Redis/Scrapy pour le premier lot.
2. SQLAlchemy **synchrone** pour l'API d'administration initiale. Le crawler futur s'exécutera dans son propre processus, avec ses limites et son propre client HTTP.
3. Sources manuelles : racines HTTP(S) `.onion` v3 strictement validées; URL et note d'autorisation enregistrées. Les sources ajoutées ne sont **pas activées pour la collecte**.
4. Stockage de métadonnées et d'extraits minimaux, pas de contenu binaire; les textes devront être purgés selon une politique de rétention.
5. Classification, gravité, pertinence et confiance sont des attributs distincts. Le score de pertinence ne prouve pas la dangerosité.
6. Les sites découverts ne sont jamais automatiquement placés dans la liste d'autorisation. Toute décision d'autorisation sera auditable.
7. La phase 1 est exclusivement locale et sans contact réseau Tor.

## Hypothèses

- Environnement de développement équipé ultérieurement de Docker Engine + plugin `docker compose`.
- Un opérateur à la fois pour le lot 0, authentifié par une clé locale. Les rôles et comptes nominatifs arrivent au lot 1.
- Seules les adresses Onion v3 sont admises; pas de support des v2, ni d'URL avec chemins arbitraires pour le registre initial.
- La collecte sera limitée à du HTML et du texte dont l'autorisation a été vérifiée. L'accessibilité publique ne suffit pas comme autorisation légale.
- Le système doit gérer l'indisponibilité fréquente des services Onion sans conclure à leur disparition.

## Risques et parades

| Risque | Parade prévue |
|---|---|
| Fuite DNS / sortie directe | Conteneur Tor isolé, SOCKS avec résolution distante, politique egress deny; tests réseau négatifs |
| SSRF / redirect hors scope | Autoriser v3 exclusivement, désactiver redirects et sous-requêtes non validées, liste d'autorisation à chaque hop |
| Contenu traumatique / illégal | Texte borné, catégorisation prudente, quarantaine sans téléchargement, signalement humain |
| Faux positifs CTI | Provenance et statut de vérification, catégorie descriptive, revue humaine |
| Perte d'état et doublons | Contraintes SQL, clé d'idempotence / empreintes, transactions |
| Migration destructive | Alembic versionné, backups, tests sur copie, restauration documentée |
| Secret API partagé | Accès loopback et clé unique provisoire; RBAC au lot 1; pas d'exposition Internet |
| Instabilité Tor | Budgets, backoff borné, état UNKNOWN distinct des erreurs permanentes |

## Critères de réussite du lot 0

- `docker compose up --build -d` démarre une API reliée à PostgreSQL (à valider sur hôte équipé Docker).
- PostgreSQL devient sain avant le démarrage de l'API; Alembic crée deux tables de départ.
- `/api/health` répond 200 et `/api/ready` prouve l'accès SQL `SELECT 1`.
- L'ajout et la liste de sources synthétiques passent par une clé API; les sources sont persistées et restent désactivées pour la collecte.
- Les doublons et URL non `.onion` v3 sont rejetés; un audit est créé lors d'une insertion valide.
- Les tests unitaires et API passent sans réseau Tor et sans PostgreSQL réel.

**Limite assumée :** un test vert sur SQLite ne prouve pas le fonctionnement PostgreSQL, Docker ou Tor. Ces validations doivent être rapportées séparément.
