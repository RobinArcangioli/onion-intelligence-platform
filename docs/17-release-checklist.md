# OIP v1.0 — décision go / no-go

| Preuve | Référence | Statut dans l'archive RC1 |
|---|---|---|
| Régression backend hors réseau | `pytest` / `docker compose ... tests` | 176/176 tests locaux réussis ; Docker chez l'opérateur à confirmer |
| Tests unitaires frontend | `npm run test:unit` | 9/9 réussis sous Node 22 |
| Tests TypeScript/Vite | `npm run build` | **Non exécuté ici**, registre npm inaccessible |
| Navigateurs Chromium | `npm run test:e2e` | Scénarios fournis ; **non exécutés ici** |
| Jeton nominatif opérationnel | `scripts/validate-v1.sh --release` | À vérifier avec jeton opérateur |
| Clé partagée désactivée | `/api/v1/auth/me`, config live | Blocage si `.env` garde `true` |
| Réseau collecteur et Tor | `scripts/check-network-isolation.sh` | Contrôles opérationnels lot 8 communiqués, à retester avec RC1 |
| Restauration temp PostgreSQL | `scripts/check-backup-restore.sh` | Réussie en lot 8 ; à retester RC1 |
| Lock npm reproductible | `frontend/package-lock.json` | **Absent de l'archive**, à générer sur poste connecté |
| Audit npm/PyPI | `scripts/audit-dependencies.sh` | **Non exécuté ici** |
| Audit images Docker | scanner d'images externe | Non exécuté |
| Restauration hors machine | exercice de reprise | Non exécuté |
| Conformité, contenu sensible, rétention | revue humaine | Non finalisé |

**Décision à la livraison : NO-GO pour revendiquer une v1.0.0 stable ou une exposition publique.**

La v1.0.0-rc1 est une candidate contrôlée pour environnement local. `--core` peut être vert sans lever les bloqueurs ci-dessus. `--release` teste plus de conditions, mais ne constitue ni une certification de sécurité ni une validation juridique.
