# Helploom dashboard

Next.js (App Router) with TypeScript strict and Tailwind CSS. It talks to the Django
backend over the REST and websocket contract in [`../docs/API.md`](../docs/API.md).

```bash
cp .env.example .env.local   # optional; the defaults match the local backend
npm install
npm run dev                  # http://localhost:3000
npm run typecheck && npm run lint && npm run build
```

Layout:

- `src/app/` routes (see `docs/DESIGN.md`, "Frontend", for the page map)
- `src/components/` hand-built UI components
- `src/lib/api/` the typed API client and the contract types
- `src/lib/auth/` the session context (in-memory access token, refresh cookie)
- `src/app/globals.css` theme tokens for light and dark mode
- `public/widget.js` the embeddable website widget
