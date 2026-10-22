# 08 — Lot 2 : collecte Tor contrôlée (v0.3.0)

## Portée et restrictions

Le collecteur **effectue au plus une requête GET vers la racine HTTP(S) d'une source Onion v3 préalablement enregistrée, approuvée, active et explicitement activée pour collecte**. Aucune collecte de liens internes ou de candidats n'est effectuée. Les candidats sont enregistrés en `PENDING` et **jamais visités automatiquement**.

Le collecteur est **désactivé par défaut** ; il ne démarre pas avec le `docker compose up -d` habituel. La commande d'exécution et une validation administrative sont nécessaires. Aucun contrôle de CAPTCHA, authentification, script, média, archive, transaction, port scanning, exploration de formulaires ou téléchargement ciblé de données privées.

Stockage : timestamp, statut HTTP 200, MIME, nombre d'octets, titre/description bornés, empreinte SHA-256 du texte normalisé, longueur du texte, adresses Onion v3 candidates dédupliquées. **Aucun corps HTML ni texte principal n'est persisté**. Les titres et descriptions peuvent toutefois contenir des données personnelles : utilisez une politique de rétention et des contrôles d'accès adéquats avant tout usage réel.

## Réseaux

```text
 Poste hôte : 127.0.0.1:8000
               |
         Nginx gateway -- ingress (sortie standard)
               |
          private (internal) ------ API et PostgreSQL
               |
           collector (one-shot) -- tor_proxy (internal) -- tor -- tor_egress (bridge)
                                    SOCKS5:9050           accès réseau externe
```

Le conteneur `collector` **n'est relié à aucun bridge externe**. Il communique avec Tor sur `tor_proxy` et avec PostgreSQL sur `private`, deux réseaux marqués `internal: true`. Seul le conteneur `tor` est connecté à `tor_egress` (bridge externe), sans port hôte exposé. La configuration Tor définit `SafeSocks 1` et `TestSocks 1`. Vérifier ces propriétés sur Docker réel avant toute collecte.

## Mise à niveau depuis le lot 1 (ne détruit pas les données)

```bash
cd ~/onion-intelligence-platform
# Décompresser l'archive du lot 2 ici sans supprimer .env ni .git.
sudo docker compose config --quiet
sudo docker compose --profile test run --build --rm tests
sudo docker compose up --build -d
sudo docker compose exec api alembic current
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/ready
```

Migration attendue : `0003_tor_collection`. Elle ajoute trois tables : `crawl_jobs`, `source_observations`, `discovered_onions`, sans supprimer les données des sources du lot 1. Les images sont construites depuis les fichiers présents, mais la compatibilité Docker/Tor réseau réelle n'a **pas** été testée dans l'environnement de génération.

## Première collecte : opération explicite

1. Choisir **uniquement** une source publique dont la consultation est autorisée. Son UUID est disponible via `GET /api/v1/sources` (en-tête `X-API-Key`). Une source nouvelle demande `POST /api/v1/sources` avec `authorization_confirmed: true` et note d'autorisation.
2. Activer la collecte pour cet UUID (ceci **ne lance aucune requête**) :

   ```bash
   curl -sS -X POST "http://127.0.0.1:8000/api/v1/sources/SOURCE_UUID/collection/enable" \
     -H "X-API-Key: VOTRE_CLE_API" -H "Content-Type: application/json" \
     -d '{"reason":"Consultation publique autorisée pour une vérification ponctuelle"}'
   ```

   Ne pas copier de clé réelle dans des journaux, captures ou historiques shell partagés. Pour une saisie non persistée, utiliser `read -rs OIP_KEY` puis `-H "X-API-Key: $OIP_KEY"` et `unset OIP_KEY`.
3. Démarrer Tor explicitement :

   ```bash
   sudo docker compose --profile tor up --build -d tor
   sudo docker compose logs --tail=100 tor
   ```

   Attendre de voir `Bootstrapped 100%` dans les journaux Tor. En cas d'échec de bootstrap, ne pas lancer le collecteur : vérifier réseau et horloge système.
4. Lancer une seule consultation du seul UUID choisi, avec un opt-in environnemental **pour cette exécution uniquement** :

   ```bash
   sudo docker compose --profile tor run --rm --build \
     -e OIP_TOR_COLLECTION_ENABLED=true collector SOURCE_UUID
   ```

   Sortie attendue si la connexion réussit : `job_id=<UUID> status=COMPLETED`. Si la source est inactive/révoquée, aucun accès Tor n'est effectué et le processus renvoie 3. Un site injoignable crée un job FAILED avec code d'erreur générique. `HTTP_NOT_OK`, `MIME_BLOCKED`, `BODY_TOO_LARGE`, `REDIRECT_BLOCKED` sont des rejets volontaires.
5. Lire les résultats via API (en-tête d'authentification nécessaire) :

   ```text
   GET /api/v1/collection/jobs
   GET /api/v1/collection/jobs/{uuid}
   GET /api/v1/collection/observations
   GET /api/v1/collection/discoveries
   ```

6. Désactiver la source si nécessaire :

   ```bash
   curl -sS -X POST "http://127.0.0.1:8000/api/v1/sources/SOURCE_UUID/collection/disable" \
     -H "X-API-Key: VOTRE_CLE_API" -H "Content-Type: application/json" \
     -d '{"reason":"Fin de la vérification ponctuelle, collecte désactivée"}'
   ```

## Paramètres de sûreté

- Domaine : uniquement racines `.onion` v3 complètes avec checksum valide ; ports et chemins arbitraires rejetés.
- Proxy figé dans le code : `socks5://tor:9050`, `trust_env=False`, aucun repli direct.
- Maximum une requête GET ; suivi des redirections désactivé.
- Types acceptés : `text/html` et `text/plain` uniquement ; contenus compressés rejetés (`Content-Encoding` différent de `identity`), octets bruts plafonnés à 256 KiB (même sans `Content-Length`).
- Timeouts de connexion/lecture/écriture configurés dans le code (`connect=35 s`, `read=25 s`, `write=10 s`), pas de retries ni de planification.
- Extraction BeautifulSoup locale sans chargement de JS, CSS ni ressources tierces ; candidat Onion repéré uniquement dans les liens `<a href>` et non téléchargé.
- Re-vérification sous verrou des autorisations **avant** la sauvegarde après récupération ; si révocation entre-temps, aucune observation ni candidate n'est persistée.
- API protégée par clé partagée `X-API-Key`; ni identité nominative ni RBAC pour le moment ; usage local uniquement.
- Les risques résiduels (corrélation Tor, métadonnées sensibles, image Tor, sortie réseau et politiques de rétention) nécessitent un examen de sécurité avant toute utilisation à grande échelle.

## Tests et limites

Tests Python/SQLite/mocks : **103 tests réussis** dans l'environnement de génération, dont simulations d'autorisation, révocation en cours de collecte, échec Tor, redirection, MIME, limite de taille et scénario migration SQLite du lot 0. Aucun réseau `.onion` n'a été utilisé ; Docker Engine, Tor réel et PostgreSQL 17 ne sont pas disponibles dans cet environnement. Il reste à valider chez l'opérateur : `docker compose config`, images, Tor bootstrap, inspection des réseaux, une consultation réellement autorisée et migration PostgreSQL 17.

Tests de sécurité à effectuer : inspection des réseaux du collecteur (aucun attachement à `tor_egress`/`ingress`), des ports Tor (aucun port publié), capture réseau sur le poste si nécessaire, vérification SafeSocks des journaux, absence d'activité HTTP si Tor indisponible. Une configuration Compose n'est pas une preuve exhaustive d'absence de fuite réseau.

## Suite

Lot 3 : crawling contrôlé des pages internes d'une source approuvée, budgets de profondeur/débit et robots policy selon périmètre autorisé, revue humaine des découvertes, suivi des changements et rétention automatique. Les fonctions de classification et d'alertes ne sont **pas** livrées au lot 2.

## Compatibilité et migration

Un test supplémentaire `test_migration_lot2_upgrade.py` migre une base SQLite déjà montée au schéma `0002_source_lifecycle` vers `0003_tor_collection` et confirme que la source préexistante reste présente et que `collection_enabled` n'est pas activé rétroactivement. Le test total exécuté est **103 passed**.
