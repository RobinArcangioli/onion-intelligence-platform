# OIP — premier déploiement OVHcloud **privé** (lot P0-A/P0-B)

> **Référence technique historique.** Pour le statut et les décisions actuels,
> consulter [l’état de référence](../../docs/ETAT_DE_REFERENCE.md) et
> [la roadmap active](../../docs/ROADMAP_ET_DECISIONS.md). Les statuts et backlogs
> ci-dessous ne constituent pas une photographie actuelle d’OVH ni une
> autorisation d’intervention.

> Statut : incrément préparatoire vérifiable, **non déployé** sur OVH.
> Ne pas lancer Tor, `collector` ou `queue_worker` avant accord contractuel spécifique.
> Aucune collecte Onion, aucun scheduler et aucun accès internet public à l'UI dans ce lot.

## Architecture P0

```
PC opérateur -- SSH (clé, IP autorisée) --> VPS OVHcloud (Ubuntu 26.04 LTS)
     navigateur http://127.0.0.1:8000    |
                      SSH -L 8000:127.0.0.1:8000
                                                |
                     loopback VPS:127.0.0.1:8000 -> Nginx gateway
                                                      | (réseau Docker private: internal)
                                                   FastAPI -> PostgreSQL (volume persistant)
```

Seul SSH doit être joignable publiquement et uniquement depuis les IP d'administration. L'hôte VPS peut sortir pour mises à jour et builds ; aucune ouverture entrante vers les ports 8000, 5432 ou 9050. Ne pas confondre le filtrage des ports publics du VPS et les politiques réseau Docker. La vérification réseau du pilote Tor sera faite ultérieurement sur l'hôte réel.

Le fichier `compose.private.yaml` est un **override non destructif** de `compose.yaml` : limites mémoire et logs bornés, drapeau global `OIP_MANUAL_COLLECTION_ENABLED=false` dans l'API, Tor inactif. Le lancement impose explicitement `db api gateway`. L'API refuse l'enqueue par un HTTP 503 si ce drapeau vaut `false` ; aucun job ne reste pendu à cause de l'absence de worker. Le validateur teste le Compose réellement résolu (sans l'imprimer).

> **Ubuntu 26.04 / VPS-1 :** utiliser d’abord le guide pas-à-pas `deploy/ovh/UBUNTU26-VPS1.md` et les scripts `bootstrap-ubuntu26.sh` + `init-env.sh`. Le présent guide décrit aussi les opérations de sauvegarde et de reprise.

## Prérequis hôte (avant toute commande de déploiement)

1. Choisir **VPS en datacenter classique** (pas Local Zone si Docker non pris en charge selon les options exactes), région, offre et budget. Base de dimensionnement : **2 vCPU, 4–8 Go de RAM, idéalement ≥80 Go SSD** ; mesurer CPU, mémoire et espace. La gamme et les prix sont susceptibles de changer ; valider le panier exact avant achat.
2. Installer une distribution Linux maintenue, installer les correctifs, créer un compte SSH nominatif avec clé, désactiver les accès root/mot de passe SSH après vérification de la connexion par clé ; conserver l'accès console de secours fournisseur. Configurer firewall hôte **et** fournisseur : autoriser SSH uniquement depuis une IP d'administration connue, rejeter les autres entrées, **y compris IPv6**. Vérifier les règles sur l'hôte réel. Ne pas ajouter les opérateurs au groupe `docker` : il offre un accès équivalent à root.
3. Installer Docker Engine et le plugin Compose **depuis les dépôts officiels Docker** ; choisir un compte technique privilégié pour les commandes Docker (par ex. `sudo -i` puis répertoire `/opt/oip` sans secrets en Git). Vérifier versions et services Docker. Installer `python3`, `curl`, `git`, `openssh-client`.
4. Préparer un dépôt source connu et vérifié et le fichier `.env` **à la racine**, hors Git et mode `0600`. `cp .env.example .env` puis saisir de nouveaux secrets distincts et longs sans passer par la ligne de commande ou les logs. `deploy/ovh/.env.example` n'est qu'un mémo. Vérifier et **renouveler réellement** les secrets anciens exposés : modifier le mot de passe PostgreSQL de l'utilisateur déjà initialisé **en base** (éditer `.env` seul n'a aucun effet sur ce compte), invalider la clé historique, révoquer/renouveler les jetons compromis. Les migrations existantes doivent être protégées par une sauvegarde avant redémarrage de l'API.
5. Avant une migration sur une base existante, vérifier un dump local protégé sur le même hôte.

## Commandes reproductibles (Linux, depuis le dépôt)

```bash
# Après création du fichier .env local secret et avant le premier lancement
chmod 600 .env
bash deploy/ovh/deploy.sh check         # pas de modification, JSON Compose jamais affiché
bash deploy/ovh/deploy.sh deploy        # build/start DB + API + UI; pas de Tor
bash deploy/ovh/deploy.sh status
bash deploy/ovh/deploy.sh smoke

# Pour déployer une nouvelle version sur une base EXISTANTE :
# 1. vérifier le dump local protégé avant migration
# 2. relever le commit/tag exact et vérifier la compatibilité Alembic
OIP_LOCAL_MIGRATION_BACKUP_VERIFIED=yes bash deploy/ovh/deploy.sh deploy

# Sur le PC opérateur (pas sur le VPS) : ouvrir une session SSH continue :
ssh -N -L 8000:127.0.0.1:8000 operateur@hote-vps
# Puis ouvrir http://127.0.0.1:8000 dans le navigateur du PC.
```

À exécuter via un compte autorisé à Docker, par exemple `sudo -i` sur le VPS, **sans transférer le jeton d'authentification dans les journaux**. La protection par jetons nominatifs reste obligatoire même via le tunnel. Créer le premier compte ADMIN uniquement après démarrage :

```bash
sudo docker compose --env-file .env -f compose.yaml -f deploy/ovh/compose.private.yaml \
  exec -T api python -m app.security.manage_users create operateur --role ADMIN --days 30
```

Le jeton ne s'affiche qu'une fois : ne pas enregistrer la sortie. Vérifier `/api/v1/auth/me` avec ce jeton, puis tester les rôles VIEWER/ANALYST/ADMIN. L'enqueue doit être refusé même pour ADMIN tant que la collecte globale est désactivée.

### Point de retour avant migration

La politique actuelle autorise un dump PostgreSQL local avant migration.
Créer l’archive sur le serveur de la base, dans un dossier protégé, puis vérifier
sa lecture avec `pg_restore --list`. En cas de besoin, valider une restauration
dans une base isolée sur ce même hôte.

## GO / NO-GO, avant accès administrateur

**GO plateforme privée uniquement** si le fournisseur/compte/offre validés, SSH restreint, firewall IPv4+IPv6 vérifié, ports applicatifs loopback confirmés sur l'hôte (`ss -ltnp`), validateur Compose PASS, secrets renouvelés, identité ADMIN nominative testée, migration `0008` vérifiée, `/api/health`, `/api/ready`, dashboard, refus 401 anonyme et refus 503 de l'enqueue testés, point de retour local vérifié avant toute migration.

**NO-GO pour Tor et la collecte**, même si l'UI est déployée : tant que les conditions contractuelles applicables (juridiction, type de VPS, contrat du compte) ne confirment pas par écrit l'autorisation d'un **client Tor privé non public** et que les contrôles réels IPv4/IPv6/DNS/SOCKS/egress ne sont pas exécutés. Les conditions OVHcloud US mentionnent une restriction incluant Tor ; ne rien en déduire automatiquement pour la France. Si refus du fournisseur, prévoir ultérieurement un collecteur séparé chez un hébergeur autorisant cette activité et connecté par canal privé, sans détournement de politique.

**NO-GO déploiement** si mot de passe DB non renouvelé sur une ancienne base, jeton compromis non révoqué, dump local non vérifié avant migration, exposition de ports non maîtrisée, conflit de profils Docker ou tests d'authentification échoués. Ne jamais faire `down -v`, `docker system prune --volumes` ou `git reset --hard` dans une procédure d'incident.

## Rollback et incidents (opérations contrôlées)

- **Incident secret / fuite** : fermer accès publics, bloquer les comptes compromis, révoquer les jetons, recréer secrets distincts avec transaction de rotation DB supervisée, revalider RBAC. Éviter tout log contenant les secrets.
- **Incident disponibilité** : conserver les volumes ; relever l'empreinte/commit de l'image, le statut des services, les erreurs expurgées et l'état d'Alembic. Ne pas supposer qu'une version applicative antérieure fonctionne sur un schéma migré.
- **Rollback applicatif** : déployer une version Git de référence dans un **worktree séparé** après validation de compatibilité DB et du point de retour local ; utiliser le même projet Compose afin de conserver les volumes, puis exécuter le smoke. Ne jamais réécrire `main` ni écraser l'historique. Si schéma incompatible : **NO-GO retour arrière automatisé**, restaurer le dump local dans une base vierge sur le même hôte, valider les données et planifier une bascule explicite avec approbation.
- **Incident base** : stopper API et gateway avec `docker compose stop api gateway` (sans `down -v`), conserver les données, valider une restauration sur clone ; obtenir l'accord de l'opérateur avant toute restauration en production.
- **Collecte incidentelle** : `docker compose --profile tor stop queue_worker collector tor`, vérifier les processus et le réseau ; sur le pilote contractuellement autorisé seulement. Le bouton ne constitue jamais une preuve d'anonymat.

## Tests automatisés et limites

```bash
python3 -m unittest discover -s deploy/ovh/tests -v
python3 -m pytest -q -p no:cacheprovider backend/tests/test_ovh_private_gate.py
bash -n deploy/ovh/deploy.sh
# Docker disponible seulement sur l'hôte cible :
bash deploy/ovh/deploy.sh check
```

Sans Docker ni accès au VPS/compte OVH, la validation du Compose **résolu**, les images construites, la migration PostgreSQL réelle, les ports du VPS, la conformité Tor restent **à vérifier**. Ce lot ne démontre aucune collecte Onion réelle.

## Décisions propriétaire à obtenir, sans bloquer le code réversible

Offre/région VPS, plafond budget et lieu d'hébergement ; autorisation contractuelle écrite de l'usage Tor prévu ; visibilité GitHub public/privé et licence ; rétention et cadre juridique ; méthode d'accès distant (SSH tunnel seul par défaut, VPN si multi-opérateurs), besoin réel éventuel d'un domaine/TLS ultérieur. Aucun nom de domaine n'est nécessaire à ce pilote privé.

### Empreintes du lot

Le manifeste `RELEASE_SHA256SUMS.txt` a été recalculé sur les **fichiers source versionnés de cette branche de travail** ; il ne décrit plus l'archive gelée de `v1.0.0-rc2` (retrouvable sur son tag conservé). Un nouveau tag produit ne doit être créé qu'après recette, vérification de l'historique et accord de publication.
