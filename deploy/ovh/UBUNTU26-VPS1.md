# OIP — installation guidée sur VPS-1 OVHcloud / Ubuntu 26.04 LTS

> **Référence technique historique.** Pour le statut et les décisions actuels,
> consulter [l’état de référence](../../docs/ETAT_DE_REFERENCE.md) et
> [la roadmap active](../../docs/ROADMAP_ET_DECISIONS.md). Les statuts et backlogs
> ci-dessous ne constituent pas une photographie actuelle d’OVH ni une
> autorisation d’intervention.

**Périmètre :** déploiement pilote **privé** `db + api + gateway`, Tor/collector/worker **désactivés** et nouvelle collecte manuelle interdite. Ce runbook n'est **pas** une preuve de déploiement sur le VPS ; inscrire les résultats réellement constatés.

## 0. Préparer les accès (sur le PC)

- Noter l'adresse IPv4 du VPS et le nom de compte de l'email de livraison OVH (habituellement `ubuntu`, pas `root`). **Ne jamais partager de mot de passe SSH, de clé privée ou de fichier `.env`.**
- Préparer une clé SSH et vérifier **une seconde connexion par clé dans une autre fenêtre** avant de désactiver un autre mode d'accès. Garder l'accès console OVH de secours disponible.
- Noter l'IP publique de ton poste (source SSH) et la règle réseau IPv6 si nécessaire. Si l'IP source change souvent, préférer ensuite un VPN privé à une ouverture SSH globale.
- Le script de bootstrap ne configure pas SSH/UFW/pare-feu fournisseur : cela évite un verrouillage de session à distance.

Connexion initiale : `ssh ubuntu@IP_DU_VPS` (adapter l'utilisateur selon l'email OVH). Si l'accès est par mot de passe initial, suivre l'invitation OVH de renouvellement puis installer et **tester** la clé avant tout durcissement.

## 1. Livrer l'archive source filtrée depuis le PC

Télécharger l'archive fournie dans la conversation et en contrôler l'empreinte SHA-256 (valeur fournie séparément avec le livrable). Depuis le dossier de téléchargement du **PC**, transférer :

```bash
scp OIP_OVH_ubuntu26_VPS1.zip ubuntu@IP_DU_VPS:~/
```

Sur le VPS, après la première connexion :

```bash
sudo apt-get update
sudo apt-get install -y unzip
sudo mkdir -p /opt/oip
sudo unzip -q ~/OIP_OVH_ubuntu26_VPS1.zip -d /opt/oip
sudo chmod 700 /opt/oip
sudo -i  # la suite des commandes sur le VPS se fait dans ce shell root
cd /opt/oip/onion-intelligence-platform
python3 scripts/verify-manifest.py
```

**Important :** l'archive filtrée ne contient ni `.env`, ni l'historique Git. Le manifeste valide le contenu versionné du lot, pas l'absence d'une compromission de l'hôte.

## 2. Installer Docker avec les paquets officiels (sur le VPS)

```bash
cd /opt/oip/onion-intelligence-platform
bash deploy/ovh/bootstrap-ubuntu26.sh
docker compose version
systemctl is-active docker
```

Le script refuse les OS autres qu'Ubuntu 26.04, vérifie la clé de signature du dépôt Docker et ne lance aucun conteneur OIP. **Ne pas ajouter `ubuntu` au groupe `docker`** : utiliser `sudo` pour les commandes de déploiement. Docker publie ses ports indépendamment de certaines règles UFW : le Compose et le port réellement écouté sont vérifiés avant/après le lancement.

## 3. SSH et pare-feu (contrôles manuels, session de secours ouverte)

Avant toute modification, vérifier une nouvelle connexion SSH par clé **depuis le PC**, sans fermer la session en cours. Pour un Ubuntu neuf, contrôler `sudo sshd -T | grep -Ei 'passwordauthentication|permitrootlogin|kbdinteractiveauthentication'` ; ne pas changer le port SSH pour ce pilote (Ubuntu 26.04 peut utiliser `ssh.socket`). Désactiver ensuite l'authentification par mot de passe et l'accès root SSH **uniquement après** vérification du second accès : éditer un fichier de configuration SSH adapté à l'ordre effectif de chargement, tester `sudo sshd -t`, recharger SSH, re-tester l'accès puis `sudo sshd -T`. Ne jamais relancer SSH à l'aveugle. Conserver le compte `ubuntu` avec privilèges sudo administratifs.

Sur Ubuntu, exemple UFW **à adapter** si SSH écoute sur 22 et si ton IPv4 source est stable :

```bash
sudo apt-get install -y ufw
sudo grep '^IPV6=' /etc/default/ufw   # attendu : IPV6=yes si IPv6 actif
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from IP_PUBLIQUE_DE_TON_PC to any port 22 proto tcp
sudo ufw --dry-run enable
# Confirmer la règle SSH dans la session actuelle et la console OVH de secours.
sudo ufw enable
sudo ufw status verbose
```

Ne **pas** copier littéralement `IP_PUBLIQUE_DE_TON_PC`. Si tu utilises aussi une connexion SSH IPv6, ajoute une règle IPv6 *avant* d'activer UFW. L'interface OVH peut également avoir un firewall réseau : n'y autoriser que SSH depuis ton IP, sans 8000/5432/9050. Ne considère pas UFW seul comme une protection des ports Docker publiés : le port Docker applicatif est explicitement lié à `127.0.0.1` et soumis au validateur fail-closed.

## 4. Initialiser la configuration et démarrer le pilote privé

```bash
cd /opt/oip/onion-intelligence-platform
bash deploy/ovh/init-env.sh
bash deploy/ovh/deploy.sh check
bash deploy/ovh/deploy.sh deploy
bash deploy/ovh/deploy.sh status
bash deploy/ovh/deploy.sh smoke
```

Si `.env` existe déjà, le générateur refuse de l'écraser. Il n'affiche pas les secrets. Les secrets propres à ce nouveau VPS ne doivent pas être transférés depuis l'ancien PC ni partagés. **Après un premier volume DB créé**, la commande `deploy` exige la vérification du dump local avant migration via `OIP_LOCAL_MIGRATION_BACKUP_VERIFIED=yes` ; ne pas forcer ce drapeau sans avoir réellement vérifié l’archive locale.

Vérifier les ports sur l'hôte :

```bash
sudo ss -ltnp | grep -E ':(22|8000|5432|9050)\\b' || true
docker compose --project-name onion-intelligence-platform --env-file .env \
  -f compose.yaml -f deploy/ovh/compose.private.yaml ps
```

**Attendu :** `127.0.0.1:8000` uniquement pour l'interface OIP ; aucune écoute publique sur `8000`, `5432`, `9050`. Le service SSH peut écouter publiquement mais son accès doit être restreint par firewall. Des conteneurs inactifs issus d'autres projets ne doivent pas être confondus avec le groupe OIP.

Créer un compte ADMIN nominatif après le premier lancement (le jeton ne sera montré qu'une fois ; ne pas copier la sortie dans un ticket/chat) :

```bash
cd /opt/oip/onion-intelligence-platform
docker compose --project-name onion-intelligence-platform --env-file .env \
  -f compose.yaml -f deploy/ovh/compose.private.yaml \
  exec -T api python -m app.security.manage_users create operateur --role ADMIN --days 30
```

## 5. Accéder à l'interface depuis ton ordinateur

Dans **un terminal du PC**, conserver ouvert :

```bash
ssh -N -L 8000:127.0.0.1:8000 ubuntu@IP_DU_VPS
```

Dans le navigateur du **PC** : `http://127.0.0.1:8000` ; l'authentification nominative reste obligatoire. Ne **pas** ouvrir `http://IP_DU_VPS:8000` ; cette adresse ne doit pas répondre.

## 6. Sauvegarde, décision GO et limites

Avant une migration, conserver un dump PostgreSQL protégé sur le même hôte et vérifier sa lecture.

GO pilote privé uniquement après : SSH clé et firewall IPv4/IPv6 validés ; `check`, `status` et `smoke` PASS ; auth nominative ; refus d'accès anonyme ; aucun service Tor/worker ; `ss` confirmant 8000 loopback ; migration Alembic vérifiée ; dump local vérifié avant migration. Tor nécessite une décision contractuelle écrite OVH et une recette réseau dédiée : ne pas lancer `--profile tor`.

**VPS-1 (4 Go/40 Go) :** surveiller `free -h`, `df -h`, `sudo docker system df` ; conserver une marge disque pour builds, journaux, Docker et PostgreSQL. Éviter les purges avec `--volumes` et toute commande de suppression de la base.
