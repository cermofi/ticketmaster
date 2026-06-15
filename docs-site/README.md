# TicketMaster — dokumentace (Fumadocs)

Samostatná dokumentační aplikace servírovaná v produkci na **`/docs/`** přes nginx → služba `docs` v Docker Compose.

## Proč samostatně

- Produkční UI je Vite + nginx na portu 3006.
- Docs potřebují Next.js a Fumadocs — běží jako vlastní kontejner, nginx proxyuje `/docs/`.

## Požadavky

- Node.js **20.9+** (doporučeno 22+)
- npm

Na serveru s Node 18 lze build spustit přes Docker:

```bash
docker run --rm -v "$PWD":/app -w /app node:22-alpine sh -c "npm install && npm run build"
```

## Příkazy

```bash
npm install
npm run dev      # http://localhost:3007/docs
npm run build
npm run start    # produkční preview na portu 3007
```

Obsah stránek: `content/docs/*.mdx` (jazyk: čeština).
