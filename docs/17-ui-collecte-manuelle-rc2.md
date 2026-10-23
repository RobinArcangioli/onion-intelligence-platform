# OIP v1.0.0-rc2 — Déclenchement manuel depuis Sources Onion

Cette livraison ajoute un **bouton par source** qui crée une seule tâche PostgreSQL, sans accès réseau dans FastAPI. La nouvelle migration **`0008_manual_queue`** ajoute un index unique partiel : au maximum un job `PENDING` ou `RUNNING` par source.

## Mise à jour non destructive

1. Sauvegarder PostgreSQL, puis extraire le ZIP à la racine du dépôt. Ne pas copier `.env` dans Git et ne pas publier de jeton.
2. Exécuter les tests et construire API/UI :

   ```bash
   cd ~/onion-intelligence-platform
   sudo bash scripts/backup-db.sh
   sudo bash scripts/validate-v1.sh --core
   sudo docker compose exec -T api alembic current
   ```

   Résultat attendu de la migration automatique au démarrage de l'API : `0008_manual_queue (head)`. La validation `--release` continue à exiger un jeton nominatif, l'audit de dépendances et Chromium.

3. **Démarrer explicitement** le consommateur de file (au lancement de la nouvelle fonctionnalité) :

   ```bash
   sudo docker compose --profile tor up --build -d tor queue_worker
   sudo docker compose logs --tail=30 tor queue_worker
   ```

   Ce démarrage n'invente aucun job et ne découvre aucune source. Le worker sonde la base privée ; seules les actions manuelles créent une tâche. Pour arrêter le consommateur : `sudo docker compose stop queue_worker`.

4. Ouvrir **http://127.0.0.1:8000/** → **Sources Onion**, s'authentifier en `ADMIN` ou `ANALYST`, et vérifier que la source est active, approuvée et que **« Autoriser collecte »** a été activé auparavant par un `ADMIN`.
5. Cliquer **« ▶ Collecter »** en face de la source souhaitée. Le statut devient `En attente…`, `En cours…`, puis `COMPLETED` ou `FAILED`. L'interface recharge le dernier job de chaque source visible environ toutes les 4 secondes.

## Garanties et restrictions

- `POST /api/v1/sources/{id}/collection/run` requiert le rôle `ANALYST` ou `ADMIN` et une justification `{"reason":"Manual check"}` (au moins 10 caractères). Réponse 202 avec `job_id` ; 401/403/409/422 en cas de refus.
- Aucune route HTTP ne lance Docker, Tor, un fetch réseau, ou ne visite des liens découverts.
- Le service `queue_worker` est sur `private` et `tor_proxy` **internes uniquement** ; pas de port publié, pas de socket Docker, pas de capacités Linux.
- Une seule racine Onion v3 approuvée est consultée par le transport Tor, sans redirection, sans médias, avec 256 Kio max ; extraction de métadonnées et mises en quarantaine inchangées.
- Révocation ou désactivation d'une source avant sa prise en charge : job `FAILED`, aucune consultation. Si une autorisation est révoquée pendant le fetch, les résultats sont écartés.
- Aucune planification périodique : les jobs naissent exclusivement d'un clic ou d'un appel API explicitement autorisé.
- **PENDING persistant** signifie souvent que le worker est arrêté. Démarrer `queue_worker` sans recliquer. Les doublons actifs renvoient 409.
- Un processus arrêté brutalement peut laisser `RUNNING`. Après avoir **arrêté le worker** et attendu au moins 60 minutes, un opérateur peut marquer ces jobs en échec, sans les rejouer :

  ```bash
  sudo docker compose stop queue_worker
  sudo docker compose --profile tor run --rm queue_worker --recover-stale
  sudo docker compose --profile tor up -d tor queue_worker
  ```

  Ne lancez pas cette réparation pendant qu'une collecte est encore en cours dans un autre worker.

## Vérification

```bash
sudo bash scripts/validate-v1.sh --core
sudo bash scripts/validate-v1.sh --release
```

Les suites backend exécutent des `fetcher` synthétiques sans réseau ; les tests Playwright vérifient seulement la présence du bouton et **ne cliquent jamais sur Collecter**. La rotation des secrets partagés antérieurement reste indispensable avant le tag stable `v1.0.0`.

Les tests de restauration sont exécutés sur une base temporaire ; pas de remplacement de la base active. Ne pas faire fonctionner une instance worker en double pendant les opérations de récupération.
