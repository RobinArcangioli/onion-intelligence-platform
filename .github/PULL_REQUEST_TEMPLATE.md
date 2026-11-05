## Objectif et périmètre

<!-- Changement limité, sans contenu ou adresse Onion réel -->

## Contrôles réalisés (ne cocher que si exécutés)

- [ ] Tests backend (commande + résultat)
- [ ] Tests frontend / build si affectés
- [ ] Tests OVH fail-closed
- [ ] Audit index des sources (ne montre aucun secret)
- [ ] Audit complet de l'historique et revue humaine avant toute publication
- [ ] Aucun secret, dump, adresse de victime ou contenu sensible dans le diff
- [ ] Autorisations/RBAC et absence de réseau Tor réel en CI vérifiés

## Migrations, exploitation et retour arrière

- [ ] Aucun impact DB ; **ou** sauvegarde externe et restauration démontrées AVANT migration
- [ ] Profil Tor désactivé et absence de nouveau port public
- [ ] Rollback décrit, sans effacement de volume ni réécriture Git
- [ ] Documentation/limitations actualisées

## Accord requis

<!-- Aucun push/publication, déploiement OVH, activation Tor, changement de licence ou politique fournisseur n'est impliqué automatiquement par l'approbation technique de la PR. -->
