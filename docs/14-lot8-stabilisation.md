# OIP — Lot 8 / v0.9.0 — Tests opérationnels et stabilisation

## Portée et changements

Cette livraison stabilise les composants déjà déployés. Elle n'ajoute ni crawler, ni source, ni canal de notification, ni migration PostgreSQL. L'objectif est de disposer de vérifications **exécutables et non destructives** avant v1.0.

- Tests synthétiques d'un flux complet : source approuvée → collecte simulée → découverte candidate → alertes → rapport figé. Aucun contenu externe et aucune connexion Tor pendant pytest.
- Test d'indisponibilité réseau : code d'erreur borné en base, aucune observation enregistrée.
- Sonde depuis **le véritable namespace réseau du collecteur** : liaison privée vers `tor:9050` et `db:5432`, impossibilité de se connecter directement à deux adresses IPv4 publiques sur HTTPS/DNS.
- Vérification de la non-publication des ports Tor sur l'hôte Docker par `docker inspect`.
- Répétition `pg_dump -Fc` → `pg_restore` dans **une nouvelle base temporaire du même serveur PostgreSQL** ; la base OIP existante n'est jamais cible du `pg_restore` ; suppression automatique de la base temporaire.
- Smoke API + dashboard via `127.0.0.1:8000` sans modifier les données et sans afficher les réponses des routes authentifiées.
- Scénarios facultatifs Playwright (écran de connexion, refus d'une clé incorrecte, navigation lecture seule pour un jeton de test). Traces/captures/vidéos désactivées.

## Installation (après commit du lot 7)

```bash
cd ~/onion-intelligence-platform
git switch -c feature/lot8-stabilization
unzip -o ~/Downloads/OIP_lot8_stabilisation_v0.9.0.zip -d .
sudo docker compose config --quiet
sudo docker compose --profile test run --build --rm tests
sudo docker compose up --build -d
sudo docker compose exec -T api alembic current
```

Résultat attendu : `0007_named_access (head)`. Aucun `alembic upgrade` nouveau n'est nécessaire.

## Validation simplifiée (commande unique)

Après extraction, sur votre machine Linux (Docker disponible), lancez :

```bash
sudo bash scripts/validate-lot8.sh
```

Ce script exécute Compose, pytest, build dashboard, smoke HTTP, contrôle du namespace collecteur et vérification d'une sauvegarde restaurée dans une base temporaire. Il démarre aussi le service Tor (mais **ne visite aucun site Onion**). Il échoue au premier contrôle qui ne passe pas. Les tests navigateur Playwright et les audits de dépendances restent optionnels et indépendants.

## Tests sur votre machine Linux

### 1. Smoke local (lecture seule)

```bash
bash scripts/smoke-local.sh
```

Ce contrôle exige des réponses HTTP 200 pour `/api/health`, `/api/ready`, et la page d'accueil, et HTTP 401 pour une requête anonyme à `/api/v1/sources`.

Les vérifications authentifiées sont optionnelles : donner à `OIP_SMOKE_TOKEN` un jeton VIEWER ou ANALYST uniquement dans le shell de test, puis l'effacer. Le script ne publie pas le jeton. Ne pas utiliser une commande `set -x` et ne pas l'inclure dans des captures de logs.

### 2. Isolation du collecteur (aucune collecte déclenchée)

```bash
sudo docker compose --profile tor up --build -d tor
sudo bash scripts/check-network-isolation.sh
```

Le script refuse tout port Tor publié. Il construit ensuite l'image du collecteur et lance **un conteneur temporaire** avec `OIP_TOR_COLLECTION_ENABLED=false` ; ce conteneur doit joindre le service Tor et PostgreSQL, mais échouer sur les connexions directes IPv4 externes. Il n'ouvre aucune URL Onion. Un échec doit bloquer la validation de la frontière réseau jusqu'à investigation.

**Limite :** il s'agit de quelques tests actifs de socket, pas d'une preuve formelle d'absence de fuite DNS ni de tous les canaux d'exfiltration. La résolution d'un nom public n'est volontairement pas tentée depuis la sonde, afin d'éviter une requête DNS inutile. Le comportement dépend de la configuration Docker, du noyau et des règles pare-feu ; refaire le contrôle après une mise à jour majeure.

### 3. Restauration de sauvegarde sans toucher à la base principale

```bash
sudo bash scripts/check-backup-restore.sh
```

Cette commande crée un **dump temporaire au format PostgreSQL**, une base `oip_restore_check_*` distincte sur le même serveur, y restaure le dump, vérifie l'existence de `alembic_version` et `onion_sources`, puis détruit la base de test et efface le dump temporaire. Elle ne prouve pas encore la restauration de tous les accès, données et configurations sur un hôte séparé. **Les fichiers `.env`, les volumes Tor et les secrets ne font pas partie du dump.**

En cas d'interruption ou d'erreur de nettoyage, le script indique le nom de la base temporaire à supprimer manuellement ; ne pas supprimer la base métier d'OIP.

### 4. Navigateur réel (facultatif)

```bash
cd frontend
npm install
npx playwright install chromium
npm run test:e2e
```

Si Chromium manque de dépendances système, suivre la sortie de `playwright install`; ne pas publier de captures contenant des données CTI. Pour le test authentifié, fournir temporairement un jeton de test via `OIP_E2E_TOKEN` sans le committer. Sans ce jeton, seul le scénario de connexion anonyme est exécuté. Le navigateur n'utilise aucun service Onion et les tests ne déclenchent pas de collecte.

### 5. Dépendances et reproductibilité

Les dépendances directes du frontend sont épinglées, mais **le graphe npm transitif n'est pas verrouillé** dans cette archive (pas de `package-lock.json`), car l'accès au registre npm était indisponible pendant la préparation. Après un build validé, exécuter `npm install --package-lock-only`, vérifier et committer `frontend/package-lock.json`, puis préférer `npm ci` pour les builds suivants.

Un audit de vulnérabilités à jour nécessite un accès aux bases d'avis de sécurité. Contrôle conseillé sur le poste de développement :

```bash
cd frontend
npm audit --omit=dev --audit-level=high
```

Auditer également les dépendances installées du backend avec un outil adapté (par exemple `pip-audit` exécuté dans un environnement isolé), ainsi que les images de base Docker. **Ces audits en ligne n'ont pas été réalisés ici** ; ne pas considérer les images et bibliothèques comme exemptes de vulnérabilités.

## Critères de validation du lot 8

1. Tests Docker backend : tous réussis.
2. API locale `/api/health`, `/api/ready`, accès anonyme refusé : conformes.
3. Contrôle runtime réseau collecteur : quatre checks PASS et aucune publication du port Tor.
4. Test `pg_dump` / restauration temporaire : PASS sans modification de la base OIP.
5. Vérification navigateur : si la dépendance Playwright est installée, tests facultatifs sans captures.
6. Nouvelle version prête pour Git : `git diff --cached --check` sans erreurs.

## Limites connues et report vers v1.0

- Révision de schéma maintenue à `0007_named_access` ; pas de nouveau mécanisme de rétention, rotation des clés ou authentification MFA.
- La clé historique est encore configurable ; la désactiver après vérification d'un jeton administrateur personnel.
- Pas de test réel de Tor hors du diagnostic SOCKS : aucun site Onion n'est visité dans ce lot.
- Vérification backup dans une base distincte mais **sur le même PostgreSQL**, pas sur un serveur indépendant ni test de reprise après panne physique.
- Une coupure brutale pendant le `pg_restore` peut laisser une base temporaire jusqu'à nettoyage manuel.
- Sans verrou transitif npm et sans audit des dépendances, la reproductibilité complète et la posture de sécurité ne sont pas encore démontrées.
- La capacité à observer de bout en bout les opérations par un navigateur devra être confirmée sur le poste opérateur.

Ne jamais présenter des tests non exécutés comme passés. La validation réelle Docker et réseau sera décidée à partir des résultats de l'opérateur.
