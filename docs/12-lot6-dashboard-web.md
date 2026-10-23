# Lot 6 — Dashboard Web (v0.7.0)

## Objet et périmètre

Interface locale React + TypeScript, servie par Nginx sur le même port que l'API : `http://127.0.0.1:8000`.

L'API FastAPI reste sur le réseau Docker privé. La base PostgreSQL, Tor et le collecteur ne sont pas publiés sur l'hôte. La passerelle est la seule entrée publique, mais elle est liée exclusivement à la boucle locale IPv4 de l'hôte.

Le dashboard est **connecté à la vraie API**, sans données de démonstration ni mock en production. Une base vide donne des vues vides explicites. Cette version n'ajoute **aucune migration de base de données** et ne lance **aucune collecte Tor** depuis un navigateur.

## Écrans et actions

| Écran | Données réellement consultées | Actions disponibles |
|---|---|---|
| Vue générale | Totaux API, 50 dernières observations, alertes ouvertes, jobs récents | Navigation |
| Sources | `/api/v1/sources` | Ajout, modification, activation/pause, approbation/révocation, activation/désactivation d'autorisation de collecte, historique, export CSV |
| Découvertes | `/api/v1/collection/discoveries` | Approbation/rejet documentaire, sans autoriser une collecte |
| Intelligence CTI | `/api/v1/cti/classifications`, `/indicators`, `/correlations` | Revue humaine des classifications |
| Watchlists | `/api/v1/watchlists` et règles | Création, activation et désactivation des règles/listes |
| Alertes | `/api/v1/alerts` | Acquittement et résolution |
| Rapports | `/api/v1/reports` | Création de snapshots bornés, export JSON/CSV authentifié |

Limites : pas de suppression de source depuis l'interface (disponible via API), ni édition des règles de watchlists hors activation ; pas de fonction d'exécution de collectes depuis l'interface. Les tableaux sont paginés, les totaux viennent des API ; l'histogramme des 7 derniers jours utilise **uniquement les 50 dernières observations chargées**, pas une requête analytique exhaustive.

## Authentification et confidentialité

- Le navigateur demande `OIP_API_KEY` à l'opérateur. Il ne lit jamais `.env`.
- Clé gardée **en mémoire React uniquement**. Pas de `localStorage`, pas de `sessionStorage`, pas de cookie.
- `X-API-Key` n'est envoyé qu'aux chemins relatifs `/api/...` sur la même origine.
- Rafraîchir l'onglet supprime la clé de la session visuelle : il faut la ressaisir.
- Toutes les requêtes sont `cache: no-store`; nginx désactive le journal d'accès HTTP pour minimiser les données d'activité sur la passerelle. Les journaux d'audit PostgreSQL existants restent inchangés.
- Le frontend n'affiche jamais de HTML brut provenant de ressources Tor ; tous les champs sont rendus par React comme texte. Les adresses Onion ne sont pas des liens cliquables.
- Les champs `reason` utilisent la valeur neutre `Manual check` et l'autorisation utilise `Manual approval` (>= 10 caractères imposés par l'API).
- CSP restreinte aux ressources locales, aucun script externe chargé par le dashboard. Les styles inline ne sont autorisés que pour les indicateurs visuels calculés côté interface.
- OIP est une application locale **mono-opérateur avec clé partagée**, et non une authentification nominative/RBAC. Ne pas exposer le port 8000 au réseau ou à Internet ; l'usage distant nécessite une couche HTTPS et d'authentification adaptée.
- Le port SOCKS de Tor n'est pas publié. La vérification préalable de l'isolation des sorties réseau du collecteur reste une opération de sécurité distincte.

## Installation/mise à niveau

```bash
cd ~/onion-intelligence-platform
git switch -c feature/lot6-dashboard-web
unzip -o ~/Downloads/OIP_lot6_dashboard_v0.7.0.zip -d .

sudo docker compose config --quiet
sudo docker compose --profile test run --build --rm tests
sudo docker compose up --build -d
```

Ouvrir `http://127.0.0.1:8000/` ; fournir la clé `OIP_API_KEY` de votre `.env` dans le formulaire de connexion, sans la partager. La documentation OpenAPI reste sur `http://127.0.0.1:8000/docs`.

Contrôles :

```bash
curl -i http://127.0.0.1:8000/
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/ready
sudo docker compose exec api alembic current  # 0006_alerts_reports (head)
```

Le front est construit lors du `docker compose up --build -d` : image de build `node:22-alpine`, installation npm, compilation TypeScript et Vite, copie du `dist/` produit dans l'image Nginx non privilégiée. Le backend ne change que son numéro de version FastAPI.

### Tests frontend hors Docker

```bash
cd frontend
npm install
npm run typecheck
npm run build
npm run test:unit
```

Les dépendances npm directes sont épinglées à des versions exactes. La génération d'un `package-lock.json` à ajouter au prochain lot est recommandée pour verrouiller également le graphe transitif. Le build dépend de l'accès au registre npm si les paquets ne sont pas déjà en cache.

## Bilan des contrôles de livraison

- 157 tests backend Python réussis hors Docker.
- 9 tests unitaires frontend Node réussis (fonctions hors React).
- Vérification syntaxique TS/TSX réussie ; contrôle type de la logique TS avec stubs minimalistes, **pas** de build Vite réel dans l'environnement de livraison (registre npm inaccessible).
- Docker Compose : YAML analysé, vérification des réseaux et ports publiée ; **pas** de démarrage Docker réel dans l'environnement de livraison.
- Aucun test end-to-end navigateur exécuté dans l'environnement de livraison. Ces vérifications sont attendues sur le poste de l'opérateur.

## Étape suivante

1. Valider le build Docker React/Vite et les 157 tests sous Docker sur le poste opérateur.
2. Vérifier connexion, sources, dossiers vides et actions d'administration sur des données fictives.
3. Figer avec un commit + tag `v0.7.0-lot6`.
4. Améliorer contrôle des sessions, RBAC, journalisation des actions nominatives et tests end-to-end avant toute exposition hors localhost.
