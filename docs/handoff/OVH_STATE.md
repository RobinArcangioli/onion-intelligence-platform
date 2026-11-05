# OVH — dernier état attesté, sans connexion au serveur

Synthèse préparée le 5 novembre 2026 (Europe/Paris), à partir des sorties
fournies par l’opérateur dans « Audit du projet OIP ». Les journaux du pilote
portent la date du 25 octobre ; leur fuseau n’est pas établi ici. Ce document
n’atteste pas l’état du serveur au 5 novembre. Aucun SSH, appel d’API OVH,
commande distante ou modification de service n’a été effectué pour cette
publication.

## Ce que les éléments disponibles attestent

- L’ancienne pièce jointe de déploiement montre `0008_manual_queue (head)`
  avant mise à niveau, puis `0017_case_notification_drafts (head)` après.
  Le contrôle du manifeste M7-C1.1 et les smoke tests ont réussi.
- La release utilisée pour le pilote se trouve sous
  `/opt/oip/releases/m7c1-1`. Le nom de projet Compose est
  `onion-intelligence-platform`. Le chemin historique de supervision reste
  `/opt/oip/onion-intelligence-platform/deploy/ovh/monitor.py` selon le plan
  local de déploiement ; son état actuel n’a pas été contrôlé.
- Un worker lancé ponctuellement avec `--once` a retourné `COMPLETED`.
  La requête SQL de l’opérateur confirme une observation enregistrée :
  HTTP `200`, `response_bytes=20788`, `text_length=117`,
  `change_status=FIRST_SEEN`. L’identifiant réel du job et l’adresse de la
  source ne sont pas nécessaires à la passation publique et sont omis.
- Après le pilote, l’API a été redémarrée avec le profil privé et la sortie
  fournie indique `MANUAL=false TOR=false`. L’arrêt du conteneur Tor est
  confirmé. Une commande d’arrêt des workers a été fournie sans inventaire
  final des conteneurs ; ne pas en déduire une preuve indépendante d’arrêt.
- Les contrôles ont retourné `PASS` pour le profil privé, `/api/health`,
  `/api/ready`, `/` et le refus de consultation anonyme des sources.
- Le moniteur a signalé un échec quand Tor fonctionnait, puis un succès après
  son arrêt : conteneurs/ports privés, santé/authentification et ressources.
  Le contrôle des sauvegardes hors site indiquait `NOT_ENABLED`.
- L’opérateur a déclaré avoir reçu l’autorisation d’OVH avant le pilote.
  Le justificatif contractuel n’a pas été fourni ni vérifié dans cette
  reprise ; aucune conclusion sur sa portée ou sa durée n’est tirée.

## Limites et points ouverts

Le profil privé du code vise `db/api/gateway` avec le seul accès hôte sur
`127.0.0.1:8000`, au moyen d’un tunnel SSH. Ce comportement est contrôlé
localement par les tests ; il ne remplace pas un inventaire réseau actuel.
OIDC/MFA, collecte permanente et planification ne sont pas attestés activés.

Le rapport 20 788 octets / 117 caractères mérite une analyse sur des exemples
synthétiques pour comprendre l’extraction ; il ne démontre ni anomalie ni
qualité suffisante. `FIRST_SEEN` est une référence initiale, pas la preuve
d’un changement entre deux collectes.

Les sauvegardes automatiques étaient reportées à la demande de l’opérateur.
Le plan de mise à niveau exigeait une sauvegarde chiffrée hors VPS et une
restauration effective ; les éléments relus ici ne suffisent pas à certifier
que cette étape a été accomplie. Ne pas confondre déploiement réussi et
qualification de reprise après sinistre. Les résultats de tests PostgreSQL
mentionnés dans les anciens plans sont des preuves historiques distinctes
des contrôles exécutés pour cette publication.

Une collecte permanente nécessiterait notamment l’adaptation de la
supervision, des essais d’interruption/redémarrage et une nouvelle recette.
Aucune commande de mise en production n’est autorisée par ce document.
