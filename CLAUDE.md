# Retail Price Monitor — CLAUDE.md

## Project Vision
Self-serve competitive price monitoring SaaS for mid-market e-commerce brands (500–50k SKUs, $1M–$100M GMV).
Target: the gap between cheap SMB tools ($99–$399/mo, no AI, daily-only) and enterprise platforms ($5k+/yr, 6-month implementation).
Price point: $299–$999/mo, self-onboard in <1 day.

## Core Differentiators
1. **AI product matching** with confidence scores + easy correction UI (not a black box)
2. **Explainable recommendations** — every alert shows WHY (which competitor, what changed, predicted impact)
3. **Tiered freshness** — hourly for "hot" categories, daily for stable ones (cost-efficient)
4. **First-class API + webhooks** — not gated to enterprise tier
5. **Native Shopify/WooCommerce repricing** — not just monitoring, closes the loop

## Target Customers (Priority Order)
1. Mid-market e-commerce retailers (own Shopify/WooCommerce store, 500–50k SKUs)
2. Brands/manufacturers needing MAP enforcement + competitive intel in one place
3. Data-savvy operators / developers wanting API-only pricing data tier

## Stack Decisions
- **Frontend**: Next.js 14 App Router, TypeScript strict, Tailwind CSS (same as stock-dashboard)
- **Scraping**: Playwright + Browserless/Browserbase for headless; Decodo/Oxylabs for proxies (buy, don't build)
- **Product matching**: OpenAI embeddings + pgvector (build — core IP)
- **Storage**: PostgreSQL (main) + TimescaleDB extension for price time-series
- **Queue**: Bull/BullMQ + Redis for scrape job scheduling
- **Alerts**: Resend (email) + Slack webhooks
- **Integrations**: Shopify OAuth app, WooCommerce REST API

## Key Market Context
- Market: $4B in 2025, growing to $12B by 2035 (11.5% CAGR)
- Main competitors: Prisync ($99–$399), Price2Spy ($24–$118), Minderest/Skuuudle (enterprise)
- Biggest gap: $300–$1000/mo self-serve tier with AI matching + API is nearly empty
- Most painful customer problem: product matching accuracy (false positives kill trust)
- Second most painful: data freshness (most SMB tools update once/day only)

## Architecture Overview
```
[Customer catalog] → [Product Matching Engine (AI)] → [Scrape Scheduler]
                                                              ↓
[Proxy Layer (Decodo/Oxylabs)] ← [Playwright Workers (K8s)] → [Raw HTML/JSON]
                                                              ↓
                                                    [Extraction + Storage]
                                                    (PostgreSQL + TimescaleDB)
                                                              ↓
                              [API + Webhooks] ← [Alerting Engine] → [Dashboard]
                                                              ↓
                                              [Repricing Connector (Shopify/WooC)]
```

## Development Phases
- **Phase 1 (MVP)**: Manual URL input + basic scraping + price history + email alerts
- **Phase 2**: AI product matching from catalog upload; Shopify integration
- **Phase 3**: Repricing automation; API + webhooks; MAP enforcement module
- **Phase 4**: AI recommendations with explainability; B2B/trade pricing

## Git & Deploy
- Author email: jkoudy@seznam.cz
- Never commit .env
- Deploy: Vercel (frontend + API routes) for MVP; migrate to dedicated infra for scraping workers

## Competitor Reference
| Tool | Price | Refresh | Matching | API |
|------|-------|---------|----------|-----|
| Prisync | $99–$399/mo | 3x/day | Basic title | Yes (higher tiers) |
| Price2Spy | $24–$118/mo | 8x/day | ML-assisted | No (CSV only) |
| PricingHunter | $99/mo | Daily | Auto | Yes |
| Pricefy | $49–$189/mo | Daily | Auto | No |
| Minderest | Custom | Continuous | AI | Yes |
| Competera | Custom | Real-time | AI+NLP | Yes |
