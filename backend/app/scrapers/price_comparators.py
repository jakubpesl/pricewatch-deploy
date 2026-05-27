from app.core.config import settings
"""
Additional European price comparators:
- Zbozi.cz (CZ)
- Geizhals.at (AT, DE)
- PriceRunner (GB, SE, DK)
- Ceneo.pl (PL)
- Trovaprezzi.it (IT)
- Arukereso.hu (HU)
- Kieskeurig.nl (NL)
- Bing Shopping (all markets)
"""
import re
import asyncio
from urllib.parse import quote_plus, urlencode
from playwright.async_api import Page
from app.scrapers.base import BaseScraper, ScrapedRetailer
import structlog

log = structlog.get_logger()


class ZboziScraper(BaseScraper):
    source_name = "zbozi"

    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        async with self:
            return await self._scrape(model_number)

    async def _scrape(self, model_number: str) -> list[ScrapedRetailer]:
        context = await self._new_context()
        page = await context.new_page()
        retailers: list[ScrapedRetailer] = []

        try:
            url = f"https://www.zbozi.cz/hledani/?q={quote_plus(model_number)}"
            await page.goto(url, timeout=settings.SCRAPE_TIMEOUT_MS)
            await self._random_delay()

            product_link = await self._find_product(page, model_number)
            if not product_link:
                return []

            await page.goto(product_link, timeout=settings.SCRAPE_TIMEOUT_MS)
            await self._random_delay()
            await self._human_scroll(page)

            page_num = 0
            while page_num < 50:
                rows = await self._extract_rows(page)
                if not rows:
                    break
                retailers.extend(rows)

                next_btn = await page.query_selector('a[rel="next"], .paginationNav-item--next')
                if not next_btn:
                    break
                await next_btn.click()
                await self._random_delay()
                page_num += 1

        finally:
            await page.close()
            await context.close()

        return retailers

    async def _find_product(self, page: Page, model_number: str) -> str | None:
        links = await page.query_selector_all('a.productCard-title, h3 a, .product-title a')
        for link in links:
            text = (await link.inner_text()).lower()
            href = await link.get_attribute("href") or ""
            if any(p in text for p in model_number.lower().split()):
                return href if href.startswith("http") else "https://www.zbozi.cz" + href
        return None

    async def _extract_rows(self, page: Page) -> list[ScrapedRetailer]:
        results = []
        rows = await page.query_selector_all('.shopOffer-item, .offer-item, [data-testid="offer"]')
        for row in rows:
            try:
                name_el = await row.query_selector('.shopOffer-shopName, .shop-name, a.shop-title')
                shop_name = (await name_el.inner_text()).strip() if name_el else ""
                link_el = await row.query_selector('a[href]')
                url = await link_el.get_attribute("href") if link_el else ""
                price_el = await row.query_selector('.shopOffer-price, .price')
                price_text = (await price_el.inner_text()).strip() if price_el else ""
                if shop_name and url:
                    results.append(ScrapedRetailer(
                        retailer_name=shop_name,
                        retailer_domain=_extract_domain(url),
                        product_url=url,
                        country_code="CZ",
                        currency="CZK",
                        price=_parse_price(price_text),
                        source=self.source_name,
                        raw_price_text=price_text,
                    ))
            except Exception:
                continue
        return results


class GeizhalsScraper(BaseScraper):
    source_name = "geizhals"

    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        async with self:
            results = []
            for country, currency in [("AT", "EUR"), ("DE", "EUR")]:
                try:
                    found = await self._scrape(model_number, country, currency)
                    results.extend(found)
                    await asyncio.sleep(2.0)
                except Exception as e:
                    log.error("geizhals.error", country=country, error=str(e))
            return results

    async def _scrape(self, model_number: str, country: str, currency: str) -> list[ScrapedRetailer]:
        context = await self._new_context()
        page = await context.new_page()
        retailers: list[ScrapedRetailer] = []

        try:
            cc = "at" if country == "AT" else "de"
            url = f"https://geizhals.{cc}/?fs={quote_plus(model_number)}"
            await page.goto(url, timeout=settings.SCRAPE_TIMEOUT_MS)
            await self._random_delay()

            product_link = await self._find_product(page, model_number, cc)
            if not product_link:
                return []

            await page.goto(product_link, timeout=settings.SCRAPE_TIMEOUT_MS)
            await self._random_delay()

            page_num = 0
            while page_num < 20:
                rows = await page.query_selector_all('.offer__merchant, .offerlist-it, [itemprop="offers"]')
                if not rows:
                    break
                for row in rows:
                    try:
                        name_el = await row.query_selector('.merchant__name, .merchant-name, a[data-merchant]')
                        name = (await name_el.inner_text()).strip() if name_el else ""
                        link_el = await row.query_selector('a[href*="http"]')
                        url_val = await link_el.get_attribute("href") if link_el else ""
                        price_el = await row.query_selector('.gh_price, .price, [itemprop="price"]')
                        price_text = (await price_el.inner_text()).strip() if price_el else ""
                        if name and url_val:
                            retailers.append(ScrapedRetailer(
                                retailer_name=name,
                                retailer_domain=_extract_domain(url_val),
                                product_url=url_val,
                                country_code=country,
                                currency=currency,
                                price=_parse_price(price_text),
                                source=self.source_name,
                                raw_price_text=price_text,
                            ))
                    except Exception:
                        continue

                next_btn = await page.query_selector('a[rel="next"]')
                if not next_btn:
                    break
                await next_btn.click()
                await self._random_delay()
                page_num += 1

        finally:
            await page.close()
            await context.close()

        return retailers

    async def _find_product(self, page: Page, model_number: str, cc: str) -> str | None:
        links = await page.query_selector_all('h2 a, .search-result-title a, a.category_list_item_text')
        for link in links:
            text = (await link.inner_text()).lower()
            href = await link.get_attribute("href") or ""
            if any(p in text for p in model_number.lower().split()):
                return href if href.startswith("http") else f"https://geizhals.{cc}{href}"
        return None


class BingShoppingScraper(BaseScraper):
    """Bing Shopping — complementary coverage to Google, different retailer set."""
    source_name = "bing_shopping"

    BING_MARKETS = [
        ("cz", "CZ", "CZK"), ("de", "de-DE", "EUR"), ("at", "de-AT", "EUR"),
        ("pl", "pl-PL", "PLN"), ("fr", "fr-FR", "EUR"), ("it", "it-IT", "EUR"),
        ("gb", "en-GB", "GBP"), ("hu", "hu-HU", "HUF"), ("nl", "nl-NL", "EUR"),
        ("es", "es-ES", "EUR"), ("se", "sv-SE", "SEK"),
    ]

    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        results: list[ScrapedRetailer] = []
        async with self:
            for cc, mkt, currency in self.BING_MARKETS:
                try:
                    found = await self._scrape_market(model_number, cc, mkt, currency)
                    results.extend(found)
                    await asyncio.sleep(2.5)
                except Exception as e:
                    log.error("bing_shopping.error", country=cc, error=str(e))
        return results

    async def _scrape_market(self, model_number: str, cc: str, mkt: str, currency: str) -> list[ScrapedRetailer]:
        context = await self._new_context()
        page = await context.new_page()
        retailers: list[ScrapedRetailer] = []

        try:
            for page_offset in range(0, 5 * 36, 36):  # 5 pages, 36 results each
                params = {"q": model_number, "cc": cc, "setmkt": mkt, "first": str(page_offset + 1)}
                url = f"https://www.bing.com/shop?{urlencode(params)}"
                await page.goto(url, timeout=settings.SCRAPE_TIMEOUT_MS)
                await self._random_delay()
                await self._human_scroll(page)

                items = await page.query_selector_all('.br-item, .pa_item, [data-bm]')
                if not items:
                    break

                for item in items:
                    try:
                        name_el = await item.query_selector('.br-sellerName, .seller-name, .pa_merchant')
                        name = (await name_el.inner_text()).strip() if name_el else ""
                        link_el = await item.query_selector('a[href]')
                        href = await link_el.get_attribute("href") if link_el else ""
                        price_el = await item.query_selector('.br-price, .pa_price, .price')
                        price_text = (await price_el.inner_text()).strip() if price_el else ""

                        if href:
                            retailers.append(ScrapedRetailer(
                                retailer_name=name or _extract_domain(href),
                                retailer_domain=_extract_domain(href),
                                product_url=href,
                                country_code=cc.upper(),
                                currency=currency,
                                price=_parse_price(price_text),
                                source=self.source_name,
                                raw_price_text=price_text,
                            ))
                    except Exception:
                        continue

        finally:
            await page.close()
            await context.close()

        return retailers


class CeneoPLScraper(BaseScraper):
    source_name = "ceneo"

    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        async with self:
            return await self._scrape(model_number)

    async def _scrape(self, model_number: str) -> list[ScrapedRetailer]:
        context = await self._new_context()
        page = await context.new_page()
        retailers: list[ScrapedRetailer] = []
        try:
            url = f"https://www.ceneo.pl/;szukaj-{quote_plus(model_number)}"
            await page.goto(url, timeout=settings.SCRAPE_TIMEOUT_MS)
            await self._random_delay()

            product_link = await page.query_selector('a.go-to-product, h3 a.product-name')
            if not product_link:
                return []
            href = await product_link.get_attribute("href") or ""
            product_url = href if href.startswith("http") else "https://www.ceneo.pl" + href

            await page.goto(product_url, timeout=settings.SCRAPE_TIMEOUT_MS)
            await self._random_delay()

            page_num = 0
            while page_num < 50:
                rows = await page.query_selector_all('.product-offers__item, .offer-item')
                for row in rows:
                    try:
                        name_el = await row.query_selector('.shop-logo img, .shop-name, [data-shop-name]')
                        name = await name_el.get_attribute("alt") if name_el else ""
                        if not name and name_el:
                            name = await name_el.inner_text()
                        link_el = await row.query_selector('a[href]')
                        url_val = await link_el.get_attribute("href") if link_el else ""
                        price_el = await row.query_selector('.price-box .value, .price')
                        price_text = (await price_el.inner_text()).strip() if price_el else ""

                        if url_val:
                            full_url = url_val if url_val.startswith("http") else "https://www.ceneo.pl" + url_val
                            retailers.append(ScrapedRetailer(
                                retailer_name=(name or "").strip(),
                                retailer_domain=_extract_domain(full_url),
                                product_url=full_url,
                                country_code="PL",
                                currency="PLN",
                                price=_parse_price(price_text),
                                source=self.source_name,
                                raw_price_text=price_text,
                            ))
                    except Exception:
                        continue

                next_btn = await page.query_selector('a[rel="next"]')
                if not next_btn:
                    break
                await next_btn.click()
                await self._random_delay()
                page_num += 1

        finally:
            await page.close()
            await context.close()

        return retailers


def _parse_price(text: str) -> float | None:
    cleaned = re.sub(r'[^\d,\.]', ' ', text).strip()
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
    match = re.match(r'https?://(?:www\.)?([^/?#]+)', url)
    return match.group(1) if match else ""


