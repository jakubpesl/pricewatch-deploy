# Deployment: Railway (backend) + Vercel (frontend)

## Potřebuješ
- Účet na GitHub (zdarma)
- Účet na Railway (zdarma, railway.app)
- Účet na Vercel (zdarma, vercel.com)

---

## Krok 1 — GitHub repo

1. Jdi na github.com → New repository → název: `retail-price-monitor`
2. Nastav na **Private**, klikni Create
3. Zkopíruj URL repo (např. `https://github.com/tvoje-jmeno/retail-price-monitor`)

Pak v terminálu:
```bash
cd /home/dellik/dev2/retail-price-monitor
git remote add origin https://github.com/tvoje-jmeno/retail-price-monitor.git
git push -u origin main
```

---

## Krok 2 — Railway backend

1. Jdi na **railway.app** → New Project → Deploy from GitHub repo
2. Vyber `retail-price-monitor` → nastavit **Root Directory**: `backend`
3. Ujisti se že Railway detekuje `Dockerfile` (měl by automaticky)

### Přidej databáze (jako Railway addony):
4. V projektu klikni **+ New** → **Database** → **PostgreSQL** → Add
5. Klikni **+ New** → **Database** → **Redis** → Add
6. Railway automaticky vloží `DATABASE_URL` a `REDIS_URL` do environment variables

### Nastav environment variables (Settings → Variables):
```
SECRET_KEY=<vygeneruj: python3 -c "import secrets; print(secrets.token_hex(32))">
ENVIRONMENT=production
FRONTEND_URL=https://tvoje-app.vercel.app   ← doplníš po kroku 3
```

7. Deploy proběhne automaticky. Po dokončení zkopíruj URL backendu
   (vypadá jako `https://retail-price-monitor-production.up.railway.app`)

### Nasaď Celery worker (druhá služba):
8. V Railway projektu klikni **+ New** → **GitHub Repo** → stejné repo
9. Root Directory: `backend`, **Start Command**: `celery -A app.workers.celery_app worker --loglevel=info --concurrency=2`
10. Sdílí stejné environment variables — přidej je ručně nebo použij Railway's "Reference Variable"

---

## Krok 3 — Vercel frontend

1. Jdi na **vercel.com** → New Project → Import z GitHubu → `retail-price-monitor`
2. **Root Directory**: `frontend`
3. **Framework Preset**: Next.js (automaticky detekuje)
4. **Environment Variables** přidej:
   ```
   BACKEND_URL=https://tvoje-railway-url.up.railway.app
   NEXTAUTH_SECRET=<vygeneruj stejně jako SECRET_KEY>
   ```
5. Deploy → za 2 minuty máš URL jako `https://retail-price-monitor.vercel.app`

---

## Krok 4 — Finální propojení

1. Zkopíruj Vercel URL → jdi zpět do Railway → Settings → Variables
2. Updatuj: `FRONTEND_URL=https://retail-price-monitor.vercel.app`
3. Railway automaticky redeploy

---

## Výsledek
- **Frontend**: `https://retail-price-monitor.vercel.app`
- **API docs**: `https://tvoje-railway-url.up.railway.app/docs`
- **Free tier limity**:
  - Railway: $5 kredit/měsíc (stačí pro prototyp)
  - Vercel: neomezené deploye, 100GB bandwidth
  - PostgreSQL: 1GB storage
  - Redis: 256MB

## Troubleshooting
- Pokud Railway build selže: zkontroluj logy, nejčastější příčina je Playwright install (potřebuje Chromium)
- Pokud scraping nefunguje: Google může blokovat Railway IP → zkus přidat Browserless.io free tier
- DB migrace: po prvním deployi spusť v Railway konzoli: `alembic upgrade head`
