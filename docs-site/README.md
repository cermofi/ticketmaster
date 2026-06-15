# TicketMaster — dokumentace (Fumadocs)

Samostatná dokumentační aplikace. Neovlivňuje produkční frontend ani Docker Compose stack.

## Proč samostatně

- Produkční UI je Vite + nginx na portu 3006.
- Docs potřebují Next.js a Fumadocs — oddělený adresář `docs-site/` drží build izolovaný.

## Požadavky

- Node.js 22+
- npm

## Příkazy

```bash
npm install
npm run dev      # http://localhost:3007/docs
npm run build
npm run start    # produkční preview na portu 3007
```

Obsah stránek: `content/docs/*.mdx` (jazyk: čeština).
