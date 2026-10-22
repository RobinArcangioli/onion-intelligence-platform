# 06 — Sécurité et conformité

## Frontières de confiance

1. **Opérateur -> API :** considérer les requêtes comme non fiables; clé API obligatoire pour tout enregistrement; Pydantic et limites de longueur.
2. **API -> PostgreSQL :** comptes et accès réseau minimaux; requêtes SQLAlchemy paramétrées; transactions et indexes uniques.
3. **PostgreSQL -> UI future :** afficher seulement des champs neutralisés; pas de rendu HTML brut, pas de secrets, pas d'exports aveugles.
4. **Crawler futur -> services Onion :** contenu non fiable, HTTP textuel sous quota, isolation et Tor exclusivement.
5. **Découvertes -> autorisations :** frontière humaine obligatoire, pas de suivi de lien automatique.

## Mesures déjà présentes

- Aucun code d'accès Tor ni crawler dans le lot 0.
- Registre limité aux racines HTTP/HTTPS `.onion` v3 avec vérification Base32/version/checksum.
- Rejet des hôtes non `.onion`, chemins, query strings, ports personnalisés et credentials URL.
- Confirmation d'autorisation explicite lors de l'ajout manuel et note requise.
- `collection_enabled=false` pour toutes les sources nouvellement créées.
- Clé API présente dans l'environnement, vérifiée en temps constant et imposée aux routes sources; longueur minimale de 32 caractères, rejet des placeholders.
- PostgreSQL et FastAPI non exposés directement à l'hôte, réseau Docker `private` interne; passerelle Nginx liée à `127.0.0.1:8000` via un réseau `ingress`. Conteneur API sans root/capacités et rootfs read-only.
- API d'administration avec entêtes `nosniff` et `no-store`.
- Journalisation métier de la création sans conserver de clé.

## Mesures impératives avant le lot Tor

- Isoler crawler, Tor et base dans des réseaux distincts; rendre impossible un egress direct au-delà de Tor (contrôle réseau indépendant de l'application).
- Tester un échec du proxy, une résolution DNS locale interdite et les redirects externes, avec capture réseau et scénarios négatifs.
- Définir des quotas de taille, de temps, de pages, de débit et de concurrence; refuser binaires et MIME douteux sans téléchargement complet.
- Interdire JavaScript, cookies de connexion, authentification, CAPTCHA bypass, accès interactifs et formulaires.
- Conserver seulement de courts extraits non sensibles; pas de récupération de bases de données volées, identifiants, archives ou médias.
- En cas de suspicion de contenu d'exploitation sexuelle de mineurs, empêcher l'exploration supplémentaire, ne pas collecter de média ni contenu, prévoir un traitement et signalement humain adaptés à la loi applicable.
- Ajouter RBAC, journal d'audit nominatif, rotation des secrets, TLS via reverse proxy privé, sauvegardes chiffrées et purge automatisée.

## Limitations connues du lot 0

- Une clé API unique, non attribuable à une personne; à remplacer par un système d'authentification et RBAC avant accès partagé.
- OpenAPI et endpoints de santé sont accessibles sur l'interface loopback; ne pas exposer le service sur une adresse publique.
- `approved_for_collection=true` dans le prototype est une déclaration d'autorisation manuelle; aucun mécanisme indépendant ne peut vérifier les droits du propriétaire du service.
- Le checker URL ne prouve pas qu'un Onion est actif ni sûr, ni que la collecte y est légale; il ne réalise aucune connexion.
- La validation v3 n'est pas un substitut aux tests SSRF applicatifs et réseau du futur crawler.
- Il reste à définir formellement les durées de conservation et la procédure de traitement des incidents sensibles.
- Le système n'est **pas prêt à être déployé sur Internet ni à scanner des services réels**.
