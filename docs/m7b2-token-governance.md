# M7-B2 — Gouvernance des jetons nominatifs (pilote privé)

## Périmètre vérifié dans le code

Ce lot conserve l'authentification par en-tête `X-API-Key` et les rôles `VIEWER`, `ANALYST`, `ADMIN`. Les jetons sont générés avec un aléa cryptographique, stockés uniquement sous empreinte SHA-256 côté base et n'existent dans le navigateur qu'en mémoire React. Il n'ajoute **ni MFA**, ni session par cookie, ni OIDC/SSO, ni migration SQL.

- `GET /api/v1/auth/tokens?limit=25&offset=0` : chaque opérateur voit uniquement les métadonnées de **ses propres** jetons. Limite de page : 1–50. Les colonnes sont l'UUID, l'étiquette d'usage, les dates de création et d'expiration, le statut et un indicateur de jeton actuel. Ni la valeur secrète ni son empreinte ne sont retournées. La clé historique partagée, lorsqu'elle reste autorisée dans un environnement de test, ne peut pas consulter cet inventaire.
- `python -m app.security.manage_users issue alice --days 30 --label laptop` : émission locale d'un jeton supplémentaire. Au maximum **cinq jetons valides non révoqués** simultanément par opérateur, sans compter les jetons expirés ou révoqués. Le jeton est imprimé une seule fois sur la sortie standard ; aucune sortie CLI ne doit être copiée dans des tickets, chats ou journaux publics.
- `python -m app.security.manage_users rotate <UUID_DU_JETON> --days 30 --label laptop` : remplacement **atomique** (dans une transaction SQL) d'un jeton actif. L'ancien jeton est immédiatement révoqué lors du commit, et la nouvelle valeur n'est affichée qu'après ce commit. La nouvelle entrée conserve l'identité et le rôle du compte. Les jetons expirés, révoqués ou appartenant à un compte désactivé ne peuvent pas être renouvelés par cette commande.
- `python -m app.security.manage_users revoke <UUID_DU_JETON>` : révocation déjà disponible dans M7-B1. La liste CLI existante inclut désormais une étiquette d'usage ; elle ne révèle aucun jeton.
- `set-role`, `disable`, `enable` : mêmes protections contre la révocation du dernier administrateur et l'usage d'anciens jetons après un changement de rôle.

## Opérations (environnement local / recette uniquement)

Exécuter le CLI **à l'intérieur du conteneur API de l'environnement de recette**, sur la base voulue ; ne pas le lancer sur le VPS OVH de production avec ce lot. Vérifier au préalable la sauvegarde et la restauration si une modification de données de production est envisagée. Ne jamais transmettre à ChatGPT les valeurs `API_TOKEN=`.

```bash
python -m app.security.manage_users list
python -m app.security.manage_users issue alice --days 7 --label workstation
python -m app.security.manage_users rotate 00000000-0000-4000-8000-000000000001 --days 7 --label workstation
python -m app.security.manage_users revoke 00000000-0000-4000-8000-000000000001
```

Les UUID dans cet exemple sont fictifs. Après rotation du jeton courant, l'interface doit être reconnectée avec le nouveau jeton ; l'ancien cesse de fonctionner. Si l'affichage du nouveau secret est perdu, un administrateur local peut en émettre un autre, sous réserve du quota.

## Limites et risques résiduels

1. Le verrou `SELECT ... FOR UPDATE` sérialise les émissions d'un même opérateur **sur PostgreSQL**, mais il faut encore valider la concurrence réelle et les commandes croisées `rotate/revoke/issue` sur PostgreSQL 17. SQLite n'applique pas les mêmes verrous.
2. L'inventaire ne fournit pas de « dernière utilisation », car la table ne l'enregistre pas ; pas de suivi de sessions persistantes côté navigateur.
3. Aucune clé de récupération secondaire ni MFA n'est introduite ; le tunnel SSH reste indispensable. L'endpoint en lecture seule est limité aux métadonnées de l'identité authentifiée.
4. Le nombre d'entrées **historiques** peut dépasser cinq : le quota ne concerne que les jetons actifs. La suppression des anciennes entrées est hors périmètre ; l'audit est conservé.
5. La commande CLI affiche un nouveau secret après le commit pour éviter d'afficher un jeton qui ne serait pas valide en base. Sa sortie doit être traitée comme un secret ; ne pas exécuter les commandes de création/rotation dans un journal CI partagé.
6. Aucune modification du gateway, aucun port ajouté, pas de Tor ni de transfert externe. Les opérations en production restent sous NO-GO jusqu'à la recette PostgreSQL et un plan de restauration vérifié.

## Recette attendue avant tout déploiement

Tests unitaires FastAPI/SQLite + frontend + audits OVH, puis PostgreSQL 17 isolé : deux émissions concurrentes alors que le compte possède déjà quatre jetons actifs ; rotation/révocation simultanées ; expiration ; révocation après changement de rôle ; liste d'identités distinctes ; essais de journalisation sans secret. Les derniers tests n'ont pas été réalisés sur un serveur PostgreSQL réel lors de cette livraison.
