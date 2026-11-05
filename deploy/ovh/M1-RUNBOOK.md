# OIP — M1 exploitation OVH (Ubuntu 26.04, VPS-1)

> **Référence technique historique.** Pour le statut et les décisions actuels,
> consulter [l’état de référence](../../docs/ETAT_DE_REFERENCE.md) et
> [la roadmap active](../../docs/ROADMAP_ET_DECISIONS.md). Les statuts et backlogs
> ci-dessous ne constituent pas une photographie actuelle d’OVH ni une
> autorisation d’intervention.

**Statut :** fichiers préparés dans une branche locale ; ne rien supposer déployé.
**Séparation stricte :** surveillance du noyau `db/api/gateway` uniquement, **aucune activation de Tor**, aucune ouverture de port, aucune CI capable d'accéder au VPS. Les commandes ci-dessous doivent être exécutées par l'opérateur après revue sur le VPS `ssh ubuntu@vps-ovh`.

## 1. Avant toute installation

- Confirmer `deploy/ovh/deploy.sh status` et `smoke` et vérifier que les ports restent privés. Sauvegarde/restauration hors VPS déjà exercées, pas de changement de secret ni migration.
- Vérifier les espaces `/var/lib/docker`, la marge mémoire VPS-1 et une seconde connexion SSH. Conserver `/opt/oip/onion-intelligence-platform/.env` **en place** (ne jamais le remplacer par le ZIP).
- Les unités ne font que **lire** les conteneurs et l'API ou générer un dump **logique** PostgreSQL. Elles ne redémarrent, ne reconstruisent et n'effacent rien. Elles nécessitent root car Docker donne un accès administrateur au système.

## 2. Installer la supervision locale

```bash
ssh ubuntu@vps-ovh
sudo -i
cd /opt/oip/onion-intelligence-platform
bash deploy/ovh/install-systemd.sh    # INSTALLE, n'ACTIVE PAS les timers
python3 deploy/ovh/monitor.py          # sonde immédiate, aucun appel externe
systemctl start oip-monitor.service
journalctl -u oip-monitor.service -n 35 --no-pager
systemctl enable --now oip-monitor.timer
systemctl list-timers 'oip-*'
```

La sonde exécute toutes les 5 minutes : états/health Docker des 3 services, ports Docker (gateway **uniquement** `127.0.0.1:8000`), absence de conteneur Tor/worker, `/api/health`, `/api/ready`, `/` et `401` sur la liste anonyme, disque Docker (alarme dès 85 %), RAM disponible (alarme si <350 MiB). Chaque résultat est écrit dans `journalctl`, jamais les contenus CTI ou secrets.

**Important :** sans destination externe configurée, `OIP_MONITOR_REQUIRE_BACKUP=0` n'atteste **pas** des sauvegardes automatiques. Le monitoring local ne suffit pas à avertir un opérateur hors ligne. Voir l'alerte facultative ci-dessous.

## 3. Préparer le backup automatique (**optionnel, pas d'activation par défaut**)

Le script existant `backup-offsite.sh` utilise `pg_dump -Fc | age | ssh` vers une **machine de sauvegarde distincte, durable et joignable**. Une sauvegarde périodique sur le même VPS **ne convient pas**. Le PC personnel ne convient comme destination automatique que s'il demeure allumé et joignable à l'heure choisie. Pour une cible SFTP/SSH ou un hôte indépendant, configurer une clé SSH **de sauvegarde à privilèges minimaux**, un dossier dédié à ce compte et un `known_hosts` vérifié par une autre voie. Préserver la clé privée **age** uniquement hors VPS.

Sur VPS :

```bash
sudo install -d -m 700 -o root -g root /etc/oip /var/lib/oip-monitor
sudoedit /etc/oip/backup.env
sudo chmod 600 /etc/oip/backup.env
sudo chown root:root /etc/oip/backup.env
```

Contenu attendu (valeurs d'exemple, **ne pas copier sans les remplacer**) :

```dotenv
OIP_BACKUP_RECIPIENT=age1CLE_PUBLIQUE_VERIFIEE
OIP_BACKUP_SSH_TARGET=backup@NOM_HOTE_SSH_VERIFIE
OIP_BACKUP_REMOTE_DIR=/srv/oip/archives
```

L'hôte de destination doit être préconfiguré et ses droits réduits ; ne pas exposer de clé privée de déchiffrement ni de jeton OIP. **Tester manuellement** :

```bash
systemctl start oip-backup.service
systemctl status oip-backup.service --no-pager
journalctl -u oip-backup.service -n 30 --no-pager
```

À partir d'une **machine de récupération séparée**, télécharger une vraie archive `.age` distante et tester :

```bash
bash deploy/ovh/verify-restore.sh /chemin/archive.dump.age /chemin/recovery-key.txt
```

Le script démarre un PostgreSQL 17 temporaire sous Docker, sans réseau ni port public, restaure **tous** les objets, vérifie Alembic `0008_manual_queue` et supprime automatiquement le conteneur test. **Ne pas l'exécuter sur le VPS de production.** Il ne doit jamais recevoir l'archive ni la clé via Git. Si le test échoue, le timer de sauvegarde reste désactivé.

**Une fois** le transfert hors VPS et la restauration réussis :

```bash
sudo systemctl enable --now oip-backup.timer
# Vérifier le marqueur local de succès (preuve de TRANSFERT uniquement) :
sudo stat /var/lib/oip-monitor/last-backup-ok
# Activer la vérification de fraîcheur uniquement après avoir vérifié le timer :
printf 'OIP_MONITOR_REQUIRE_BACKUP=1\n' | sudo tee /etc/oip/monitor.env >/dev/null
sudo chmod 600 /etc/oip/monitor.env
sudo systemctl start oip-monitor.service
```

Si le dernier transfert réussi remonte à plus de 36 heures, la sonde échoue. Ce marqueur **n'est pas** une preuve de restauration et ne remplace pas un exercice régulier de reprise. Définir une politique de rétention côté stockage externe et une répétition mensuelle de restauration ; ne jamais effacer des archives automatiquement avant validation des contraintes de rétention.

## 4. Alertes hors VPS (facultatif et explicitement activé)

Par défaut, `OnFailure` écrit seulement dans le journal : **aucun email ni webhook externe** n'est configuré. Pour des alertes réellement reçues hors VPS, préparer un point de terminaison webhook maîtrisé et créer **manuellement**, sous root, `/etc/oip/alert.curl`, mode `0600`, avec par exemple :

```text
url = "https://URL-PRIVEE-DU-WEBHOOK"
request = "POST"
```

Ce fichier est **hors du dépôt** ; il peut contenir un token dans l'URL, à garder secret. `notify-failure.sh` n'envoie que `event` et `unit` (jamais de données CTI). Vérifier la bonne réception d'un incident de test sans provoquer de panne réelle : `sudo bash deploy/ovh/notify-failure.sh oip-test.service`. Pour tout webhook externe, valider préalablement la confidentialité, la destination et le réseau. Si le webhook n'est pas configuré, consulter régulièrement `systemctl --failed` et `journalctl` : la supervision seule n'envoie aucune notification.

## 5. Vérifier après activation

```bash
sudo systemctl list-timers 'oip-*'
sudo systemctl --failed
sudo journalctl -u oip-monitor.service -n 35 --no-pager
sudo journalctl -u oip-backup.service -n 35 --no-pager
sudo bash deploy/ovh/deploy.sh status
sudo bash deploy/ovh/deploy.sh smoke
sudo ss -lntp | grep -E ':(8000|5432|9050)\b' || true
```

### Incident, arrêt et rollback M1

- **Alerte disque / RAM / indisponibilité :** relever logs expurgés et état du VPS ; ne pas purge de volumes, ne pas lancer Tor, ne pas automatiser de redémarrage ou de rollback.
- **Arrêter uniquement l'automatisation M1**, sans toucher aux conteneurs : `sudo systemctl disable --now oip-monitor.timer oip-backup.timer`. Les services déjà en cours peuvent continuer jusqu'à leur fin ; les arrêter manuellement si nécessaire (un dump en cours peut être interrompu sans toucher la base).
- **Rollback des unités :** désactiver timers, supprimer après revue uniquement `/etc/systemd/system/oip-{monitor,backup}.{timer,service}` et `/etc/systemd/system/oip-alert@.service`, puis `systemctl daemon-reload`. Ne pas effacer `/etc/oip/`, la clé SSH, les archives hors site, `/var/lib/oip-monitor` ou la base PostgreSQL par automatisme.
- **Déploiement applicatif :** ne pas activer une chaîne de déploiement direct GitHub → VPS. Pour toute mise à niveau, respecter le garde-fou du script `OIP_BACKUP_VERIFIED=yes` **uniquement après exercice de restauration** et vérifier la compatibilité Alembic.

## 6. CI GitHub (lecture seule, sans déploiement)

`.github/workflows/oip-ci.yml` exécute les tests Python/OVH et le build frontend sur PR/push. **Aucun SSH, secret OVH, Tor, migration réelle ou `docker deploy` n'y est autorisé.** Avant tout `git push`, résoudre le NO-GO documentaire déjà signalé sur l'historique Git destiné à devenir public ; choisir la visibilité du dépôt et appliquer la politique de revue. L'état réel de GitHub Actions ne peut être confirmé que sur GitHub après publication autorisée.

## Critères M1 à mesurer sur VPS (pas revendiqués par la livraison locale)

- Timer de surveillance actif, aucun service Tor, endpoints locaux et règles de ports conformes.
- Sauvegarde automatique chiffrée hors VPS, un exemplaire distant réellement téléchargé et **restauré**, timer de sauvegarde actif, fraîcheur <36 h.
- Alerte réellement reçue hors VPS (ou accepter explicitement une astreinte manuelle).
- Procédure d'arrêt/rollback des timers testée, politique de rétention et RPO/RTO documentés.
- CI GitHub verte sur branche privée autorisée, sans aucun secret ni accès OVH.
