from app.core.config import settings
"""
Idealo scraper — covers DE, AT, FR, IT, ES, GB, PL markets.
Idealo aggregates thousands of shops per product.
Strategy: search → product detail → paginate "Alle Angebote" tab.
"""
import re
import asyncio
from urllib.parse import quote_plus
from playwright.async_api import Page
from app.scrapers.base import BaseScraper, ScrapedRetailer
import structlog

log = structlog.get_logger()

IDEALO_SITES = [
    {"base": "https://www.idealo.de", "country": "DE", "currency": "EUR"},
    {"base": "https://www.idealo.at", "country": "AT", "currency": "EUR"},
    {"base": "https://www.idealo.fr", "country": "FR", "currency": "EUR"},
    {"base": "https://www.idealo.it", "country": "IT", "currency": "EUR"},
    {"base": "https://www.idealo.es", "country": "ES", "currency": "EUR"},
    {"base": "https://www.idealo.co.uk", "country": "GB", "currency": "GBP"},
    {"base": "https://www.idealo.pl", "country": "PL", "currency": "PLN"},
]


class IdealoScraper(BaseScraper):
    source_name = "idealo"

    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        results: list[ScrapedRetailer] = []
        async with self:
            for site in IDEALO_SITES:
                try:
                    found = await self._scrape_site(model_number, site)
                    results.extend(found)
                    log.info("idealo.done", country=site["country"], found=len(found))
                    await asyncio.sleep(2.0)
                except Exception as e:
                    log.error("idealo.error", country=site["country"], error=str(e))
        return results

    async def _scrape_site(self, model_number: str, site: dict) -> list[ScrapedRetailer]:
        context = await self._new_context()
        page = await context.new_page()
        retailers: list[ScrapedRetailer] = []

        try:
            search_url = f"{site['base']}/preisvergleich/MainSearchProductCategory.html?q={quote_plus(model_number)}"
            await page.goto(search_url, timeout=settings.SCRAPE_TIMEOUT_MS)
            await self._random_delay()

            product_link = await self._find_best_product(page, model_number, site["base"])
            if not product_link:
                return []

            await page.goto(product_link, timeout=settings.SCRAPE_TIMEOUT_MS)
            await self._random_delay()
            await self._human_scroll(page)

            retailers = await self._extract_all_offers(page, site)

        except Exception as e:
            log.error("idealo._scrape_site.error", error=str(e))
        finally:
            await page.close()
            await context.close()

        return retailers

    async def _find_best_product(self, page: Page, model_number: str, base: str) -> str | None:
        selectors = [
            'a.sr-resultList__item--title',
            'a[data-testid="sr-productname"]',
            '.sr-resultList__item a',
            'h2.sr-resultList__item-name a',
        ]
        model_lower = model_number.lower()
        for selector in selectors:
            links = await page.query_selector_all(selector)
            for link in links:
                text = (await link.inner_text()).lower()
                href = await link.get_attribute("href") or ""
                if any(part in text for part in model_lower.split()):
                    return href if href.startswith("http") else base + href
        return None

    async def _extract_all_offers(self, page: Page, site: dict) -> list[ScrapedRetailer]:
        retailers: list[ScrapedRetailer] = []

        # Click on "Alle Angebote" / "All offers" tab
        try:
            offers_tab = await page.query_selector(
                'a[href*="angebote"], button:has-text("Alle Angebote"), '
                'a:has-text("Alle Angebote"), a:has-text("All offers"), '
                'a:has-text("Toutes les offres"), a:has-text("Tutte le offerte")'
            )
            if offers_tab:
                await offers_tab.click()
                await self._random_delay()
        except Exception:
            pass

        # Paginate through all offer pages
        page_num = 0
        while page_num < 50:  # safety cap
            page_retailers = await self._extract_offer_rows(page, site)
            retailers.extend(page_retailers)

            next_btn = await page.query_selector(
                'a[rel="next"], button[aria-label*="nächste"], '
                '.pagination__item--next:not([disabled]), [data-testid="pagination-next"]'
            )
            if not next_btn or not page_retailers:
                break

            await next_btn.click()
            await self._random_delay()
            page_num += 1
            log.info("idealo.pagination", country=site["country"], page=page_num)

        return retailers

    async def _extract_offer_rows(self, page: Page, site: dict) -> list[ScrapedRetailer]:
        retailers: list[ScrapedRetailer] = []
        row_selectors = [
            '.productOffers-listItem',
            '.offerList-item',
            '[data-testid="offer-listitem"]',
            '.offer-list-item',
        ]

        rows = []
        for selector in row_selectors:
            rows = await page.query_selector_all(selector)
            if rows:
                break

        for row in rows:
            try:
                name_el = await row.query_selector(
                    '.productOffers-listItemShopLogo, .shop-name, [data-testid="shop-name"], '
                    '.logo, img[alt]'
                )
                shop_name = ""
                if name_el:
                    shop_name = await name_el.get_attribute("alt") or await name_el.inner_text()
                    shop_name = shop_name.strip()

                link_el = await row.query_selector('a[href]')
                product_url = ""
                if link_el:
                    href = await link_el.get_attribute("href") or ""
                    product_url = href if href.startswith("http") else site["base"] + href

                price_el = await row.query_selector(
                    '.productOffers-listItemOfferPrice, .price, [data-testid="price"]'
                )
                price_text = (await price_el.inner_text()).strip() if price_el else ""
                price = _parse_price(price_text)

                if product_url:
                    domain = _extract_domain(product_url)
                    retailers.append(ScrapedRetailer(
                        retailer_name=shop_name or domain,
                        retailer_domain=domain,
                        product_url=product_url,
                        country_code=site["country"],
                        currency=site["currency"],
                        price=price,
                        source=self.source_name,
                        raw_price_text=price_text,
                    ))
            except Exception as e:
                log.debug("idealo.row_parse_error", error=str(e))

        return retailers


def _parse_price(text: str) -> float | None:
    cleaned = re.sub(r'[^\d,\.]', ' ', text).strip()
    cleaned = re.sub(r'\s+', '', cleaned)
    if ',' in cleaned and '.' not in cleaned:
        cleaned = cleaned.replace(',', '.')
    elif ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace('.', '').replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_domain(url: str) -> str:
    match = re.match(r'https?://(?:www\.)?([^/?#]+)', url)
    return match.group(1) if match else ""


