from app.core.config import settings
"""
Heureka scraper — covers CZ + SK aggregators.
Heureka aggregates 20,000+ shops. Strategy:
  1. Search model number → get product detail page
  2. On product page, click "Všechny nabídky" → paginate through ALL offers
  3. Extract every individual shop with their direct URL
"""
import re
import asyncio
from urllib.parse import urlencode, quote
from playwright.async_api import Page
from app.scrapers.base import BaseScraper, ScrapedRetailer
import structlog

log = structlog.get_logger()

HEUREKA_SITES = [
    {"base": "https://www.heureka.cz", "country": "CZ", "currency": "CZK",
     "search": "/hledej.php?h%5Bfraze%5D={query}"},
    {"base": "https://www.heureka.sk", "country": "SK", "currency": "EUR",
     "search": "/hladaj.php?h%5Bfraze%5D={query}"},
]


class HeurekaScraper(BaseScraper):
    source_name = "heureka"

    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        results: list[ScrapedRetailer] = []
        async with self:
            for site in HEUREKA_SITES:
                try:
                    found = await self._scrape_site(model_number, site)
                    results.extend(found)
                    log.info("heureka.discover", site=site["base"], found=len(found))
                except Exception as e:
                    log.error("heureka.discover.error", site=site["base"], error=str(e))
        return results

    async def _scrape_site(self, model_number: str, site: dict) -> list[ScrapedRetailer]:
        context = await self._new_context()
        page = await context.new_page()
        retailers: list[ScrapedRetailer] = []

        try:
            search_url = site["base"] + site["search"].format(query=quote(model_number))
            await page.goto(search_url, timeout=settings.SCRAPE_TIMEOUT_MS)
            await self._random_delay()

            # Find best matching product on search results page
            product_link = await self._find_product_link(page, model_number)
            if not product_link:
                log.info("heureka.no_product_found", model=model_number, site=site["base"])
                return []

            # Navigate to product detail
            await page.goto(product_link, timeout=settings.SCRAPE_TIMEOUT_MS)
            await self._random_delay()
            await self._human_scroll(page)

            # Extract all offers with full pagination
            retailers = await self._extract_all_offers(page, site)

        except Exception as e:
            log.error("heureka._scrape_site.error", error=str(e))
        finally:
            await page.close()
            await context.close()

        return retailers

    async def _find_product_link(self, page: Page, model_number: str) -> str | None:
        """Find the most relevant product on the search results page."""
        # Heureka search results: product cards with links
        selectors = [
            'a.c-product-list__title',
            'a[data-testid="product-title"]',
            'h2 a',
            '.product__title a',
        ]
        model_lower = model_number.lower()
        for selector in selectors:
            links = await page.query_selector_all(selector)
            for link in links:
                text = (await link.inner_text()).lower()
                href = await link.get_attribute("href")
                if href and any(part in text for part in model_lower.split()):
                    return href if href.startswith("http") else f"https://www.heureka.cz{href}"
        return None

    async def _extract_all_offers(self, page: Page, site: dict) -> list[ScrapedRetailer]:
        """
        Navigate to "all offers" tab and paginate through every shop.
        Heureka shows top 5 by default; "Všechny nabídky" reveals all.
        """
        retailers: list[ScrapedRetailer] = []

        # Click "all offers" button if present
        try:
            all_offers_btn = await page.query_selector(
                'a[href*="nabidky"], a[href*="ponuky"], [data-testid*="offer"], a:has-text("Všechny nabídky"), a:has-text("Všetky ponuky")'
            )
            if all_offers_btn:
                href = await all_offers_btn.get_attribute("href")
                if href:
                    all_offers_url = href if href.startswith("http") else site["base"] + href
                    context = page.context
                    offers_page = await context.new_page()
                    try:
                        await offers_page.goto(all_offers_url, timeout=settings.SCRAPE_TIMEOUT_MS)
                        await self._random_delay()
                        # Paginate through all offer pages
                        page_num = 1
                        while True:
                            page_retailers = await self._extract_offer_rows(offers_page, site)
                            retailers.extend(page_retailers)

                            # Check for next page
                            next_btn = await offers_page.query_selector(
                                'a[rel="next"], .c-pagination__next:not([disabled]), a:has-text("Další"), a:has-text("Ďalšia")'
                            )
                            if not next_btn or page_num >= 50:  # safety cap
                                break
                            next_href = await next_btn.get_attribute("href")
                            if not next_href:
                                break
                            next_url = next_href if next_href.startswith("http") else site["base"] + next_href
                            await offers_page.goto(next_url, timeout=settings.SCRAPE_TIMEOUT_MS)
                            await self._random_delay()
                            page_num += 1
                            log.info("heureka.offers_pagination", page=page_num)
                    finally:
                        await offers_page.close()
                    return retailers
        except Exception as e:
            log.warning("heureka.all_offers_nav_failed", error=str(e))

        # Fallback: extract offers directly from product page
        return await self._extract_offer_rows(page, site)

    async def _extract_offer_rows(self, page: Page, site: dict) -> list[ScrapedRetailer]:
        """Extract retailer offers from current page."""
        retailers: list[ScrapedRetailer] = []

        # Multiple possible offer row selectors across Heureka versions
        row_selectors = [
            '.c-offer-list__item',
            '.offer-item',
            '[data-testid="offer-item"]',
            '.shop-offer-item',
        ]

        rows = []
        for selector in row_selectors:
            rows = await page.query_selector_all(selector)
            if rows:
                break

        for row in rows:
            try:
                # Extract shop name
                shop_name_el = await row.query_selector(
                    '.c-offer-list__shop-name, .shop-name, [data-testid="shop-name"], a.shop-title'
                )
                shop_name = (await shop_name_el.inner_text()).strip() if shop_name_el else "Unknown"

                # Extract direct URL to the shop's product page
                link_el = await row.query_selector('a[data-testid*="shop-link"], a.c-offer__shop-link, a[href*="exit"]')
                if not link_el:
                    link_el = await row.query_selector('a[href]')
                product_url = ""
                if link_el:
                    href = await link_el.get_attribute("href")
                    if href:
                        product_url = href if href.startswith("http") else site["base"] + href

                # Extract price
                price_el = await row.query_selector(
                    '.c-offer-list__price, .price, [data-testid="price"], .c-price'
                )
                price_text = (await price_el.inner_text()).strip() if price_el else ""
                price = _parse_price(price_text)

                # Extract availability
                stock_el = await row.query_selector('.c-offer-list__availability, .availability, [data-testid="availability"]')
                stock_text = (await stock_el.inner_text()).strip().lower() if stock_el else ""
                in_stock = "skladem" in stock_text or "na sklade" in stock_text or "available" in stock_text

                if shop_name and product_url:
                    domain = _extract_domain(product_url)
                    retailers.append(ScrapedRetailer(
                        retailer_name=shop_name,
                        retailer_domain=domain,
                        product_url=product_url,
                        country_code=site["country"],
                        currency=site["currency"],
                        price=price,
                        in_stock=in_stock,
                        source=self.source_name,
                        raw_price_text=price_text,
                    ))
            except Exception as e:
                log.debug("heureka.row_parse_error", error=str(e))
                continue

        return retailers


def _parse_price(text: str) -> float | None:
    """Extract numeric price from localized price string like '12 990 Kč' or '199,99 €'."""
    cleaned = re.sub(r'[^\d,\.]', ' ', text).strip()
    cleaned = re.sub(r'\s+', '', cleaned)
    # Handle Czech/SK format: 12 990 → 12990; 199,99 → 199.99
    if ',' in cleaned and '.' not in cleaned:
        cleaned = cleaned.replace(',', '.')
    elif ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_domain(url: str) -> str:
    match = re.match(r'https?://(?:www\.)?([^/]+)', url)
    return match.group(1) if match else url


# Avoid circular import
