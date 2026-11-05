# Backlog OIP 2026 — ordre de dépendance pour un déploiement réel

Échelle relative : XS < S < M < L < XL. La **valeur** et le **risque** sont qualitatifs, non des promesses de calendrier. Les durées du document de passation (J0–J5, S1–S16+) sont à revalider après premiers essais en infrastructure.

| Ordre / issue | Dépend de | Taille | Valeur utilisateur | Risque principal | Critère d'acceptation concret |
|---|---|---|---|---|---|
| #01 Audit baseline et secrets (P0-A) | — | M | Confiance de départ haute | Réutilisation secret | Git/RC2/versions confirmés ; rotation DB effective, clé legacy invalidée, comptes nominaux, audit sensible sans valeurs exposées |
| #02 **Bootstrap OVH privé (P0-B)** | #01 | M | Première application réellement accessible | Port exposé / perte de données | `check` PASS, API/DB/UI en accès SSH local, migrations et auth testées sur VPS, worker absent |
| #03 Sauvegarde externe et exercice de reprise (P0-B) | #02 | M | Durabilité | Copie inutilisable | Dump chiffré distant, restauration complète validée sur hôte vierge, RPO/RTO consignés |
| #04 CI déterministe et scanner supply chain (M0) | #01 | L | Livraisons reproductibles | Faux PASS | PR lance tests offline backend/frontend, vérif. migration PostgreSQL, Gitleaks/audits, build verrouillé, artefact signé si pertinent |
| #05 Staging OVH et rollback testé (M0/M1) | #02,#03,#04 | M | Mise à jour contrôlée | Migration incompatible | Promotion manuelle staging→pilote, rollback image et procédure DB documentés/testés |
| #06 Conformité fournisseur Tor (P0-C) | #02 | S | Décision de déploiement légitime | Violation contractuelle | Réponse explicite OVH pour offre/région/compte ; si refus, architecture collecteur externe conforme |
| #07 Isolation egress et kill switch sur hôte réel (P0-C) | #06 | L | Collecte gouvernée | Fuite IP/DNS ou fallback | IPv4/IPv6/DNS/SOCKS prouvés, aucun accès direct ni SOCKS public, stop effectif, preuves expurgées |
| #08 Pilote clic manuel de bout en bout (P0-C) | #07,#03 | M | Premier cas d'usage démontré | Source non autorisée | Source de démonstration autorisée, clic→PENDING→COMPLETED, empreinte/observation affichée, audit et limites |
| #09 Supervision minimale et runbooks (M1) | #02,#03 | M | Support opérationnel | Incident silencieux | Uptime, DB, disque, mémoire, queue, erreurs et seuils ; incident simulé diagnostiqué |
| #10 File robuste et backpressure (M2) | #08 | L | Résilience collecte | Jobs bloqués / doublons | Leases, heartbeats, retries bornés, annulation, reprise DB/Tor et tests de concurrence |
| #11 Scheduler opt-in gouverné (M3) | #10 | L | Veille automatique cadrée | Surcollecte | Activation ADMIN/source+expiration/budget, aucun défaut actif, kill switch et audit 100 % des jobs |
| #12 Recherche, provenance, diff et rétention (M4) | #08,#10 | XL | Analyse changements | Données excessives | Requête source/date/catégorie, résultats paginés, provenance, purge testée |
| #13 IOC/CTI expliquables (M5) | #12 | L | Corrélation exploitable | Faux positifs | IOC normalisés et sourcés, confiance distincte gravité, revue humaine, export traçable |
| #14 Workflow analyste et alerting (M6) | #12,#13 | L | Passage détection→action | Notifications sensibles | Triage/assignation/notes/notifications minimisées, historique RBAC et clôture testés |
| #15 IAM et sécurité équipe (M7) | #04,#14 | XL | Utilisation multi-opérateur | Autorisation insuffisante | Modèle de menace, SSO/MFA selon besoin, rôles testés, politiques de rétention et DAST/SAST |
| #16 SLO, charge, reprise et release finale (M8/M9) | #09,#10,#15 | XL | Produit exploitable | Charge/support | SLO, coûts, tests de charge sans Tor réel, documentation externe, recette utilisateur et release signée |

**Règle de livraison** : pour chaque issue, fournir diff/commit, tests exécutés et non exécutés, migration et rollback, documentation opérateur, risques résiduels et GO/NO-GO. Aucune découverte Onion ne doit être promue automatiquement en source.
