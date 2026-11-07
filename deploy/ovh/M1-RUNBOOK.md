# OIP — Supervision locale

Ce runbook décrit les contrôles sur l’hôte OIP. Les opérations sur OVH
restent soumises au GO prévu dans la [roadmap](../../docs/ROADMAP_ET_DECISIONS.md).
La supervision écrit dans le journal local. La politique de données autorise
uniquement les dumps locaux avant migration.

## Profils

- **private** attend `db`, `api` et `gateway`, avec la collecte manuelle
  désactivée dans l’API.
- **manual** attend aussi `tor` et `queue_worker`, avec la collecte manuelle
  activée dans l’API. Le scheduler et le collecteur ponctuel restent arrêtés.

Le seul port publié est `127.0.0.1:8000`. Pour valider le Compose manuel en
recette locale, appliquer les overlays dans cet ordre. Le JSON résolu contient
des secrets et doit rester dans le pipe.

```bash
set -o pipefail
docker compose --profile tor -f compose.yaml -f deploy/ovh/compose.private.yaml \
  -f deploy/ovh/compose.manual.yaml config --format json |
  python3 deploy/ovh/check_compose.py --profile manual
python3 deploy/ovh/monitor.py --profile manual
```

## Journal et alertes

L’installation des unités copie les fichiers. L’activation du timer se fait
séparément, après choix du profil. Le profil par défaut est `private`.
Pour la supervision du profil manuel, définir `OIP_MONITOR_PROFILE=manual`
dans `/etc/oip/monitor.env`.

```bash
sudo bash deploy/ovh/install-systemd.sh
sudo systemctl start oip-monitor.service
sudo journalctl -u oip-monitor.service -n 35 --no-pager
sudo systemctl enable --now oip-monitor.timer
```

Le timer contrôle toutes les cinq minutes. Un incident nouveau produit un
`WARN`, puis un `ALERT` s’il persiste au contrôle suivant. Le retour à la
normale produit `RECOVERED`. Le contrôle ponctuel sans fichier d’état
signale les incidents dès leur constat. Aucun diagnostic ne contient d’URL
de source, de contenu collecté ou de secret.

- `WORKER_PULSE_STALE` signale une boucle worker sans activité récente.
- `TOR_PROXY_UNAVAILABLE` signale l’absence de réponse au salut SOCKS local.
  Ce contrôle ne renseigne pas sur l’accessibilité d’une destination Onion.
- `QUEUE_NOT_PROGRESSING` indique qu’un job éligible attend depuis cinq
  minutes alors qu’une place est disponible. Les URL qui attendent leur tour
  derrière une autre URL du même groupe sont exclues.
- `QUEUE_LEASE_EXPIRED` indique qu’un job en cours n’a plus de bail valide.
- `WORKER_CHECK_UNAVAILABLE` signale un échec du contrôle worker ou de sa
  lecture de PostgreSQL.

Un délai d’attente Tor ou un circuit ouvert sur une source reste consultable
dans le résultat de cette veille.

## Arrêt et reprise

1. Relever `docker compose --profile tor ps` et le journal local. En cas
   d’arrêt prolongé, désactiver l’admission de nouveaux jobs dans l’API.
2. Stopper le worker et tout collecteur ponctuel. Vérifier qu’aucun autre
   worker ne tourne avant toute réconciliation.
3. Inspecter les jobs abandonnés. Après confirmation de l’arrêt, les clore
   avec la commande explicite de réconciliation. Seuls les jobs assez anciens
   dont le bail a expiré sont concernés.
4. Redémarrer le worker, vérifier la sonde et rétablir l’admission si elle a
   été suspendue. Les URL encore en attente continuent. Les tentatives
   interrompues conservent leur état d’échec.

```bash
docker compose --profile tor stop queue_worker collector
docker compose --profile tor run --rm --no-deps queue_worker --inspect-stale --stale-minutes 5
docker compose --profile tor run --rm --no-deps queue_worker --recover-stale \
  --stale-minutes 5 --confirm-worker-stopped
docker compose --profile tor up -d queue_worker
python3 deploy/ovh/monitor.py --profile manual
```

Pour suspendre le timer seul, utiliser
`sudo systemctl disable --now oip-monitor.timer`.
