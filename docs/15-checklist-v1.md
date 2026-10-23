# OIP — Préconditions avant de déclarer v1.0 stable

Le lot 8 constitue une candidate de stabilisation, **pas** une certification de sécurité.

| Contrôle | Preuve attendue avant v1.0 | Statut à la livraison |
|---|---|---|
| Tests de régression Python | Tous les tests passent dans `docker compose --profile test run --build --rm tests` | Testés localement hors Docker |
| Intégration navigateur | Connexion VIEWER/ANALYST, navigation, logout ; tests Chrome headless | En attente sur poste opérateur |
| Frontend build | `docker compose up --build -d` et dashboard servi | En attente sur poste opérateur |
| Isolation Tor | Aucun port Tor publié, sorties IPv4 directes refusées | Sonde fournie, en attente |
| Continuité Tor | Échec de Tor traité sans connexion directe ni données sensibles | Tests synthétiques uniquement |
| Données | Dump PostgreSQL restaure sur base temporaire | Script fourni, en attente |
| Reprise après sinistre | Copie chiffrée du dump, secrets et procédure testée sur serveur distinct | Non validé |
| Clé partagée | `OIP_LEGACY_API_KEY_ENABLED=false` et compte admin nominatif opérationnel | À confirmer sur poste opérateur |
| Dépendances | Audit de vulnérabilités images, PyPI et npm ; versions verrouillées | Non validé (réseau indisponible) |
| Mises à jour | Revue des composants et des régressions | À planifier |
| Légalité et contenu sensible | Politique de rétention, signalement et supervision humaine | À compléter |

**Go/no-go :** ne pas annoncer une mise en production ouverte ou exposée à Internet. Le service reste local `127.0.0.1:8000`, et toute collecte doit être soumise à autorisation explicite.
