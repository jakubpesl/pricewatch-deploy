from app.core.config import settings
"""
Product page scraper — given a known retailer URL, extracts:
  - Current price + original price
  - In-stock status
  - Rating + review count
  - Screenshot

This runs in Phase 2 (post-discovery) for every found URL.
Uses httpx for simple pages, Playwright for JS-rendered ones.
"""
import re
import asyncio
import base64
from urllib.parse import urlparse
from playwright.async_api import Page
from app.scrapers.base import BaseScraper, ScrapedRetailer
import httpx
from bs4 import BeautifulSoup
import structlog

log = structlog.get_logger()

# JSON-LD price patterns (structured data — most reliable)
JSONLD_PRICE_RE = re.compile(r'"price"\s*:\s*"?([0-9]+(?:[.,][0-9]+)?)"?', re.IGNORECASE)
# Microdata
META_PRICE_RE = re.compile(r'itemprop="price"\s+content="([0-9]+(?:[.,][0-9]+)?)"', re.IGNORECASE)
# Common price element CSS patterns
PRICE_SELECTORS = [
    # Generic
    '[data-price]', '[data-product-price]', '.product-price', '.price',
    # Schéma.org
    '[itemprop="price"]', '[itemprop="offers"] [itemprop="price"]',
    # Shopify
    '.product__price', '.price__regular', '[data-product-price]',
    # WooCommerce
    '.woocommerce-Price-amount', '.price ins',
    # Czech/Slovak shops
    '.price-box', '.cena', '.product-price__value',
    # German shops
    '.price--highlight', '.buybox__price', '.a-price-whole',
]

STOCK_SELECTORS = [
    '[itemprop="availability"]',
    '.availability', '.stock', '.product-availability',
    '[data-availability]',
]

IN_STOCK_TEXTS = [
    'in stock', 'available', 'skladem', 'na sklade', 'auf lager',
    'disponible', 'disponibile', 'en stock', 'na stanie', 'in magazzino',
]


class ProductPageScraper(BaseScraper):
    source_name = "direct"

    async def scrape_price(self, url: str, country_code: str) -> ScrapedRetailer | None:
        """
        Scrape a single product page. Tries fast httpx first, falls back to Playwright.
        Returns None if unable to extract price.
        """
        # Phase 1: try fast httpx (works for ~40% of sites — server-rendered pages)
        result = await self._try_httpx(url, country_code)
        if result and result.price:
            return result

        # Phase 2: Playwright for JS-rendered sites
        return await self._try_playwright(url, country_code)

    async def _try_httpx(self, url: str, country_code: str) -> ScrapedRetailer | None:
        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
                },
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None

                html = resp.text
                price = self._extract_price_from_html(html)
                in_stock = self._extract_stock_from_html(html)
                domain = _extract_domain(url)

                return ScrapedRetailer(
                    retailer_name=domain,
                    retailer_domain=domain,
                    product_url=url,
                    country_code=country_code,
                    currency=_guess_currency(url, country_code),
                    price=price,
                    in_stock=in_stock,
                    source=self.source_name,
                )
        except Exception as e:
            log.debug("product_page.httpx_failed", url=url, error=str(e))
            return None

    def _extract_price_from_html(self, html: str) -> float | None:
        # 1. JSON-LD structured data (most reliable)
        m = JSONLD_PRICE_RE.search(html)
        if m:
            return _parse_price(m.group(1))

        # 2. Microdata itemprop
        m = META_PRICE_RE.search(html)
        if m:
            return _parse_price(m.group(1))

        # 3. BeautifulSoup CSS selectors
        soup = BeautifulSoup(html, "lxml")
        for selector in PRICE_SELECTORS:
            el = soup.select_one(selector)
            if el:
                text = el.get("content") or el.get("data-price") or el.get_text(strip=True)
                price = _parse_price(text)
                if price and 0.01 < price < 1_000_000:
                    return price

        return None

    def _extract_stock_from_html(self, html: str) -> bool | None:
        soup = BeautifulSoup(html, "lxml")
        # JSON-LD availability
        if '"InStock"' in html or '"in_stock"' in html:
            return True
        if '"OutOfStock"' in html or '"out_of_stock"' in html:
            return False
        for selector in STOCK_SELECTORS:
            el = soup.select_one(selector)
            if el:
                text = el.get("content", "") or el.get_text(strip=True).lower()
                if any(t in text.lower() for t in IN_STOCK_TEXTS):
                    return True
        return None

    async def _try_playwright(self, url: str, country_code: str) -> ScrapedRetailer | None:
        async with self:
            context = await self._new_context()
            page = await context.new_page()
            try:
                await page.goto(url, timeout=settings.SCRAPE_TIMEOUT_MS, wait_until="domcontentloaded")
                await self._random_delay()
                await self._human_scroll(page)

                price = await self._extract_price_playwright(page)
                in_stock = await self._extract_stock_playwright(page)
                rating, review_count = await self._extract_rating_playwright(page)
                screenshot = await self._take_screenshot(page)
                domain = _extract_domain(url)

                return ScrapedRetailer(
                    retailer_name=domain,
                    retailer_domain=domain,
                    product_url=url,
                    country_code=country_code,
                    currency=_guess_currency(url, country_code),
                    price=price,
                    in_stock=in_stock,
                    rating=rating,
                    review_count=review_count,
                    source=self.source_name,
                    extra={"screenshot_base64": screenshot},
                )
            except Exception as e:
                log.error("product_page.playwright_failed", url=url, error=str(e))
                return None
            finally:
                await page.close()
                await context.close()

    async def _extract_price_playwright(self, page: Page) -> float | None:
        # Try JSON-LD via page.evaluate
        try:
            price_from_jsonld: float | None = await page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const s of scripts) {
                        try {
                            const d = JSON.parse(s.textContent);
                            const offers = d.offers || (d['@graph'] || []).flatMap(n => n.offers || []);
                            const offer = Array.isArray(offers) ? offers[0] : offers;
                            if (offer && offer.price) return parseFloat(String(offer.price).replace(',', '.'));
                        } catch {}
                    }
                    return null;
                }
            """)
            if price_from_jsonld and 0.01 < price_from_jsonld < 1_000_000:
                return price_from_jsonld
        except Exception:
            pass

        # Fallback: CSS selectors
        for selector in PRICE_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el:
                    text = await el.get_attribute("content") or await el.inner_text()
                    price = _parse_price(text.strip())
                    if price and 0.01 < price < 1_000_000:
                        return price
            except Exception:
                continue

        return None

    async def _extract_stock_playwright(self, page: Page) -> bool | None:
        for selector in STOCK_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el:
                    text = (await el.inner_text()).lower()
                    content = (await el.get_attribute("content") or "").lower()
                    combined = text + " " + content
                    if any(t in combined for t in IN_STOCK_TEXTS):
                        return True
                    if "out" in combined or "outofstock" in combined:
                        return False
            except Exception:
                continue
        return None

    async def _extract_rating_playwright(self, page: Page) -> tuple[float | None, int | None]:
        try:
            rating_el = await page.query_selector('[itemprop="ratingValue"], .rating-value, .stars')
            review_el = await page.query_selector('[itemprop="reviewCount"], .review-count, .reviews-count')
            rating = None
            count = None
            if rating_el:
                text = await rating_el.get_attribute("content") or await rating_el.inner_text()
                try:
                    rating = float(text.strip().replace(',', '.'))
                except ValueError:
                    pass
            if review_el:
                text = await review_el.get_attribute("content") or await review_el.inner_text()
                m = re.search(r'\d+', text)
                count = int(m.group()) if m else None
            return rating, count
        except Exception:
            return None, None

    async def _take_screenshot(self, page: Page) -> str | None:
        try:
            data = await page.screenshot(type="jpeg", quality=60, clip={"x": 0, "y": 0, "width": 1366, "height": 800})
            return base64.b64encode(data).decode()
        except Exception:
            return None


def _parse_price(text: str) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r'[^\d,\.\s]', '', str(text)).strip()
    cleaned = re.sub(r'\s+', '', cleaned)
    if not cleaned:
        return None
    if ',' in cleaned and '.' not in cleaned:
        cleaned = cleaned.replace(',', '.')
    elif ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace('.', '').replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_domain(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return domain.replace("www.", "")


def _guess_currency(url: str, country_code: str) -> str:
    cc = country_code.upper()
    mapping = {
        "CZ": "CZK", "PL": "PLN", "GB": "GBP", "HU": "HUF",
        "SE": "SEK", "DK": "DKK", "RO": "RON", "NO": "NOK",
    }
    return mapping.get(cc, "EUR")


