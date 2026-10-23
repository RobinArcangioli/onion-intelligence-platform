# Guide utilisateur — Onion Intelligence Platform

*OIP v1.0.0-rc2 · Usage local · Version de référence du code gelé*

Bienvenue dans OIP. Ce guide couvre les actions quotidiennes depuis l'interface, sans manipulation de conteneurs. Pour installer le service ou gérer les identités, consultez le [guide d'administration](installation-administration.md).

## 1 · Accéder à votre espace

1. Demandez à un administrateur un **jeton personnel** actif. N'utilisez pas une clé partagée historique.
2. Ouvrez **http://127.0.0.1:8000/** sur la machine hébergeant OIP.
3. Collez le jeton dans **CLÉ API**, puis cliquez sur **Accéder au dashboard**.
4. Vous retrouvez votre identité et votre rôle en haut de l'interface.

**Confidentialité :** le jeton est conservé en mémoire dans cette session React ; il n'est pas écrit dans `localStorage` ou un cookie. L'actualisation complète de l'onglet nécessite une nouvelle connexion. Utilisez **Déconnecter** en quittant votre poste, puis fermez l'onglet.

### Qui peut faire quoi ?

| Action | VIEWER | ANALYST | ADMIN |
|---|:---:|:---:|:---:|
| Consulter les données, historiques, signaux et rapports | ✓ | ✓ | ✓ |
| Demander une collecte ponctuelle d'une source autorisée | — | ✓ | ✓ |
| Gérer le registre, les autorisations et les comptes | — | — | ✓* |

\* Les comptes et jetons sont administrés dans le terminal local par un administrateur du serveur ; l'interface web ne gère pas les identités.

## 2 · Prendre en main l'interface

Le menu latéral propose sept espaces :

| Espace | À quoi sert-il ? |
|---|---|
| **Vue générale** | Synthèse des sources, observations récentes, alertes et derniers jobs. Les graphiques sont indicatifs et issus d'un échantillon, pas d'une statistique exhaustive. |
| **Sources Onion** | Registre, recherche, ajout, approbation, activation et **▶ Collecter** par source. |
| **Découvertes** | Adresses candidates extraites des pages autorisées ; revue humaine avant toute inclusion au registre. |
| **Intelligence CTI** | Classifications heuristiques et indicateurs avec provenance/état de vérification. |
| **Watchlists** | Expressions de veille et règles pondérées utilisées pour analyser les observations. |
| **Alertes** | Événements dédupliqués à traiter ou clôturer. |
| **Rapports** | Snapshots de métadonnées et exports JSON/CSV bornés. |

Les tableaux sont paginés, leurs filtres peuvent être modifiés. Le bouton d'actualisation en haut recharge l'espace courant. Les résultats reflètent la base réelle : OIP n'invente pas de détections lorsqu'aucune collecte n'a eu lieu.

## 3 · Ajouter une source Onion (ADMIN)

Dans **Sources Onion**, choisissez **Ajouter une source**. Saisissez :

- **Nom** : désignation compréhensible et neutre.
- **URL** : racine exacte d'un service `.onion` v3 ; les chemins, identifiants, ports personnalisés et URL non Onion sont refusés.
- **Description** et **priorité** : contexte de veille, sans données personnelles inutiles.
- **Autorisation explicite** : confirmez que vous êtes habilité à consulter cette source publique. L'API exige également une justification d'autorisation ; l'interface fournit une note neutre en anglais.

Une source nouvellement enregistrée est **approuvée au registre, mais non autorisée à la collecte** (`collection_enabled=false`). Cette séparation est intentionnelle : enregistrer une source ne déclenche aucun accès réseau.

Les actions d'administration (modification, approbation, retrait, désactivation, restauration) sont journalisées. Les sources supprimées peuvent être restaurées par la procédure prévue, selon les droits disponibles.

## 4 · Collecter maintenant : le parcours recommandé

**Avant le premier clic**, un administrateur du serveur doit avoir démarré le service `queue_worker` derrière Tor. Pour la source visée, vérifiez les trois conditions : **active**, **approuvée** et **collecte autorisée**. Seul `ADMIN` peut changer ces autorisations ; `ANALYST` peut exécuter la collecte autorisée.

1. Ouvrez **Sources Onion** et recherchez la source.
2. Contrôlez son statut et son autorisation ; sélectionnez **Autoriser collecte** si vous êtes `ADMIN` et que le périmètre est toujours valide.
3. Cliquez sur **▶ Collecter** sur **cette ligne uniquement**.
4. L'interface affiche **En attente…** puis **En cours…** ; elle interroge l'état de la tâche environ toutes les **4 secondes**.
5. À la fin, consultez le job puis ses observations et les espaces de veille associés.

```text
Clic explicite ─→ API (RBAC + approbation) ─→ job PENDING en PostgreSQL
       └──────→ worker isolé ─→ Tor SOCKS ─→ racine Onion approuvée
                                            └→ métadonnées / observations / alertes
```

Un seul job `PENDING` ou `RUNNING` peut exister par source ; le bouton est temporairement indisponible si une tâche active existe. **Aucune collecte périodique n'est planifiée** : démarrer le worker ne crée pas de nouvelles tâches, mais il peut traiter des jobs déjà en attente.

**Limites :** une collecte effectue au plus une requête sur la racine autorisée, sans suivre les liens découverts, sans média ni archive, avec taille et délais bornés. Les contenus bruts des pages ne sont pas conservés. N'utilisez pas OIP pour accéder à des services privés, contourner une authentification ou récupérer des données volées.

### Comprendre les statuts

| Statut | Interprétation | Action recommandée |
|---|---|---|
| `PENDING` | Demande enregistrée ; worker pas encore passé | Attendez ; si le statut persiste, contactez l'administrateur pour vérifier `queue_worker`. |
| `RUNNING` | Job revendiqué par le worker | Ne recliquez pas. |
| `COMPLETED` | Traitement terminé | Examinez les observations et changements ; cela ne garantit pas un contenu pertinent. |
| `FAILED` | Refus, interruption ou erreur générique | Faites vérifier le journal du worker ; évitez d'enchaîner les tentatives sans diagnostic. |

## 5 · Exploiter les résultats

**Observations.** Une réponse peut produire un titre, une description, un type MIME, un code HTTP, un horodatage, une empreinte de texte et un indicateur de changement. Un résultat vide ou une erreur réseau n'est pas une preuve de disparition du service.

**Découvertes.** Les nouvelles URL sont des **candidates**, pas de nouvelles sources à crawler. Vérifiez leur légitimité et l'autorisation nécessaire avant toute approbation ; le système ne les visite pas automatiquement.

**Intelligence CTI.** Les catégories et indicateurs reposent sur des règles et sur les données accessibles. Les niveaux de confiance et de pertinence ne doivent pas être confondus. L'état de vérification reste central : ne présentez aucune observation comme un fait criminel établi sans investigation indépendante.

**Watchlists.** Créez des expressions et règles adaptées à vos besoins de veille. Testez les faux positifs ; une occurrence de mot ne prouve aucune activité illicite.

**Alertes.** Consultez les alertes ouvertes, examinez la source et la provenance, puis accusez réception ou clôturez selon les autorisations. Des alertes peuvent être dédupliquées ; l'absence d'alerte ne signifie pas absence de risque.

**Rapports.** Sélectionnez une plage temporelle et, si nécessaire, une source ; générez un rapport et exportez ses métadonnées en JSON ou CSV. Vérifiez le périmètre et les limites de lignes avant diffusion. Les exports peuvent contenir des URL et observations sensibles : ne les joignez jamais à un ticket ou dépôt public.

## 6 · Bonnes pratiques

- Travaillez exclusivement avec des sources **explicitement autorisées**. Revérifiez l'autorisation avant la collecte.
- Commencez avec **une seule source de test** et contrôlez la chaîne des résultats avant d'élargir le périmètre.
- Ne copiez pas de jetons, d'URL sensibles, de dumps SQL ou de captures authentifiées dans GitHub ou des outils publics.
- Le dashboard est **local**, pas conçu pour être directement exposé sur Internet.
- Signalez toute anomalie à l'administrateur, en donnant un **code d'erreur et un horodatage**, pas un secret ou un corps de page.

## 7 · Aide rapide

| Symptôme | Vérifications |
|---|---|
| La connexion est refusée | Jeton expiré/révoqué, rôle ou utilisateur désactivé, clé historique non acceptée. Demandez une réémission. |
| « ▶ Collecter » est grisé | Rôle `VIEWER`, source inactive/non approuvée, collecte non autorisée, ou job actif. |
| La collecte reste « En attente… » | Le worker Tor peut être arrêté. Contactez l'administrateur ; ne multipliez pas les clics. |
| Le job échoue | Vérifier Tor, l'autorisation toujours valide, la connectivité interne et les logs *sans afficher de secrets*. |
| Une découverte ne s'ouvre pas | C'est normal : OIP ne visite pas les liens détectés. |
| Une alerte paraît incorrecte | Examinez provenance, règle, confiance et vérification ; ne tirez pas de conclusion automatique. |
| La page est vide après rechargement | Les jetons ne sont pas persistés ; reconnectez-vous. |

Pour la mise en route ou le diagnostic avancé, poursuivez dans le [guide d'installation et d'administration](installation-administration.md).
