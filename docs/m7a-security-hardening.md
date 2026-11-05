# M7-A — Frontière HTTP, permissions et modèle de menace (hors production)

> **Repère historique de lot.** Les statuts de déploiement, validations et suites
> annoncées ci-dessous décrivent la rédaction de ce guide. Pour l’état actuel
> de référence, lire [État de référence](ETAT_DE_REFERENCE.md) et
> [Roadmap et décisions](ROADMAP_ET_DECISIONS.md). La décision MVP du
> 5 novembre 2026 prévoit un admin connecté par jeton API individuel et une vitrine
> visiteur limitée ; ce modèle n’est pas encore implémenté. Ce guide
> n’autorise aucune action OVH.

## Périmètre, état et décision

Ce lot porte uniquement sur le proxy Nginx et l'API FastAPI, ainsi que sur des tests de **régression RBAC**. Aucun changement de schéma ni migration, aucune collecte Tor, aucun envoi externe et aucune nouvelle surface réseau. La sauvegarde automatisée du VPS reste reportée à la demande du propriétaire. **Ne pas déployer sur la production OVH sans contrôles préalables et procédure de retour arrière**.

Le déploiement pilote prévu reste une UI privée via `ssh -N -L 8000:127.0.0.1:8000 ubuntu@vps-ovh`. Le nouvel ingress n'admet que les en-têtes Host `localhost` et `127.0.0.1`. Les accès via un nom DNS/VPN personnalisé nécessitent une **évaluation et une modification explicites de l'allowlist avant mise en service** ; ne pas désactiver la vérification sous prétexte de compatibilité. Les adresses directes sur Internet restent interdites.

## Frontières de confiance et menaces

| Frontière | Menace envisagée | Défense et limites |
|---|---|---|
| Navigateur ↔ Nginx | DNS rebinding, hôtes trompeurs, clickjacking, cache involontaire | Allowlist Host, CSP, `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `no-store`; non substituable à une revue XSS |
| Nginx ↔ API | Exposition de la documentation non authentifiée | Réponses 404 sur `/docs`, `/redoc`, `/openapi.json` au gateway ; l'API interne garde ces routes pour les tests locaux |
| Client ↔ API | Usage abusif d'un jeton, lecture non autorisée, écriture par rôle insuffisant | Jetons personnels existants, RBAC serveur, nouveaux tests d'inventaire des routes et accès VIEWER ; rotation, révocation et audit toujours essentiels |
| Navigateur ↔ contenu CTI | Scripts et contenus actifs issus de sources externes | Aucune HTML brute conservée, interdiction des scripts tiers, CSP `object-src 'none'`; les champs textuels doivent continuer à être traités comme non fiables |
| VPS ↔ réseaux externes | Exposition ou utilisation de Tor sans conformité | Déploiement privé, Tor et scheduler désactivés ; conformité contractuelle non résolue |
| Base de données ↔ application | Perte de données à la mise à jour | Aucune migration M7-A ; migrations M2–M6 en attente de validation PostgreSQL 17 + restauration pré-migration |

## Changements vérifiables

1. L'ingress Nginx refuse les hôtes inattendus (`421`) et masque les trois endpoints de documentation (`404`). Aucune authentification API n'est supprimée.
2. Les en-têtes CSP, anti-frame, no-referrer, no-store, Permissions-Policy et CORP sont maintenant appliqués au **niveau du serveur** Nginx, y compris aux erreurs, sans en-têtes spécifiques aux emplacements qui annuleraient l'héritage.
3. Le middleware FastAPI impose `Cache-Control: no-store`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` et `Cross-Origin-Resource-Policy` également sur 401. La CORS reste fermée : aucun `Access-Control-Allow-Origin` ajouté.
4. Les tests introspectent **toutes les routes /api/v1/**, exigent l'authentification, un contrôle de rôle sur chaque écriture, et une vérification de rôle sur les lectures sensibles. Un test fonctionnel soumet chaque écriture avec un jeton VIEWER valide et attend 403.
5. La CI installe `nginx-core` pour vérifier la syntaxe via un fichier temporaire. Les contrôles n'ont pas besoin de DNS Docker ni de réseau Onion ; le nom de l'upstream n'est remplacé que dans la **copie de test**.

## Commandes de validation hors production

```bash
cd backend
python3 -m pytest -q tests/test_m7a_http_security.py
cd ..
python3 -m unittest discover -s deploy/ovh/tests -q
# Recommandé sur hôte de test : nginx et npm présents
cd frontend && npm run test:unit && npm run build
```

Un test manuel local peut lancer une instance Nginx jetable sur un port **127.0.0.1 dédié**, avec une copie temporaire remplaçant l'upstream `api` par `127.0.0.1`. Les comportements attendus sont : `/docs` et `/openapi.json` → 404, Host étranger → 421, réponses contenant `Cache-Control: no-store`, `X-Frame-Options: DENY` et CSP. Aucun besoin de démarrer le collecteur ou Tor.

## Critères GO avant toute installation sur OVH

- Faire confirmer qu'aucun accès légitime ne dépend d'un nom d'hôte autre que `localhost` ou `127.0.0.1`.
- Exécuter la CI sur une copie autorisée du dépôt ; l'audit historique de publication publique reste distinct et bloquant selon la politique en vigueur.
- Vérifier le comportement du navigateur via **tunnel SSH**, la disponibilité API, les refus 401/403, le fonctionnement des exports et les headers de réponse.
- Disposer d'une sauvegarde/restauration hors VPS **vérifiée avant toute opération ultérieure risquant les données** ; pour M7-A, le changement ne touche pas le volume Postgres, mais un rollback applicatif testé reste obligatoire.
- Documenter le retour arrière : préserver le Compose et les images précédentes, redéployer uniquement Nginx et l'API à partir d'artefacts vérifiés ; ne pas exécuter Alembic ni supprimer un volume.

## Dette de sécurité ouverte — hors M7-A

- L'authentification repose sur des jetons personnels stockés uniquement en mémoire côté React : **pas de SSO/OIDC, MFA, sessions fédérées ni workflow de récupération**.
- L'API expose toujours la documentation via **son interface interne** : l'interdiction du gateway n'est pas un contrôle pour les clients qui accèdent au réseau Docker.
- Le débit Nginx de `10r/s` est partagé par IP source ; via tunnel SSH, plusieurs utilisateurs peuvent avoir la même IP apparente. Ce n'est **pas** une limitation de débit par utilisateur.
- Les logs d'audit ne sont pas infalsifiables ; aucune preuve d'immutabilité ou de collecte SIEM n'est fournie.
- Aucun audit DAST/SAST complet, test d'intrusion, contrôle des en-têtes TLS publics ni test de sécurité de bout en bout en production n'a été réalisé.
- Les éventuelles extensions VPN/DNS, la TLS externe, le stockage des secrets, les autorisations granulaires par ressource, la politique de rétention et l'isolation multi-tenant nécessitent une conception et des tests séparés.
