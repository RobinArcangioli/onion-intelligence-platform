# OIP Dashboard (React + TypeScript)

Interface locale de v0.9.0. La clé API est gardée uniquement en mémoire React ; elle n'est jamais codée en dur dans le bundle.

Depuis la racine du dépôt, privilégier `sudo docker compose up --build -d` : une construction frontend multi-étapes compile l'interface et la sert par le conteneur `gateway`, sur `127.0.0.1:8000`.

Pour un développement hors Docker (avec API locale existante) :

```bash
cd frontend
npm install
npm run dev  # http://127.0.0.1:5173 ; proxy /api vers localhost:8000
npm run typecheck
npm run build
npm run test:unit
```

Les dépendances directes sont épinglées, mais le graphe transitif n'est pas verrouillé sans `package-lock.json` ; en créer un depuis une installation npm validée, puis le versionner avant les prochains déploiements. En production, Nginx sert le contenu compilé et transmet seulement les requêtes `/api/`, `/docs`, `/openapi.json`, `/redoc` à FastAPI.

Ne jamais écrire `OIP_API_KEY` dans les fichiers frontend, une URL ou une capture d'écran. Aucun résultat n'est inventé en l'absence de données.

## Browser smoke (optional, requires local running OIP)

```bash
cd frontend
npm install
npx playwright install chromium
npm run test:e2e
```

La connexion avec un jeton personnel est optionnelle : définir `OIP_E2E_TOKEN` temporairement pour vérifier les vues authentifiées. Ne jamais enregistrer ce jeton dans Git, les captures, les traces ou les sorties de test. Playwright est désactivé par défaut dans le workflow Docker.
