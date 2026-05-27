from app.core.config import settings
"""
Google Shopping scraper — covers ALL European markets.
Strategy:
  - Run query for each EU country with gl= parameter
  - Paginate through at least 5 pages (each page = ~40 results)
  - Covers every shop with Google Shopping feed (from giants to small e-shops)
  - Use localized queries per market for better coverage
"""
import re
import asyncio
from urllib.parse import urlencode, quote_plus
from playwright.async_api import Page
from app.scrapers.base import BaseScraper, ScrapedRetailer
import structlog

log = structlog.get_logger()

EU_MARKETS = [
    {"gl": "cz", "hl": "cs", "country": "CZ", "currency": "CZK", "buy_word": "koupit"},
    {"gl": "sk", "hl": "sk", "country": "SK", "currency": "EUR", "buy_word": "kúpiť"},
    {"gl": "de", "hl": "de", "country": "DE", "currency": "EUR", "buy_word": "kaufen"},
    {"gl": "at", "hl": "de", "country": "AT", "currency": "EUR", "buy_word": "kaufen"},
    {"gl": "pl", "hl": "pl", "country": "PL", "currency": "PLN", "buy_word": "kup"},
    {"gl": "fr", "hl": "fr", "country": "FR", "currency": "EUR", "buy_word": "acheter"},
    {"gl": "it", "hl": "it", "country": "IT", "currency": "EUR", "buy_word": "acquistare"},
    {"gl": "gb", "hl": "en", "country": "GB", "currency": "GBP", "buy_word": "buy"},
    {"gl": "hu", "hl": "hu", "country": "HU", "currency": "HUF", "buy_word": "vásárlás"},
    {"gl": "ro", "hl": "ro", "country": "RO", "currency": "RON", "buy_word": "cumpara"},
    {"gl": "nl", "hl": "nl", "country": "NL", "currency": "EUR", "buy_word": "kopen"},
    {"gl": "be", "hl": "fr", "country": "BE", "currency": "EUR", "buy_word": "acheter"},
    {"gl": "es", "hl": "es", "country": "ES", "currency": "EUR", "buy_word": "comprar"},
    {"gl": "se", "hl": "sv", "country": "SE", "currency": "SEK", "buy_word": "köpa"},
    {"gl": "dk", "hl": "da", "country": "DK", "currency": "DKK", "buy_word": "køb"},
    {"gl": "fi", "hl": "fi", "country": "FI", "currency": "EUR", "buy_word": "osta"},
]

MAX_PAGES_PER_MARKET = 5  # 5 pages × ~40 results = ~200 results per market


class GoogleShoppingScraper(BaseScraper):
    source_name = "google_shopping"

    async def discover(self, model_number: str, markets: list[str] | None = None) -> list[ScrapedRetailer]:
        """
        Discover retailers across European markets via Google Shopping.
        markets: list of country codes to scan (None = all EU markets)
        """
        target_markets = [m for m in EU_MARKETS if markets is None or m["country"] in markets]
        results: list[ScrapedRetailer] = []

        async with self:
            # Run markets sequentially to avoid getting blocked (each has random delay)
            for market in target_markets:
                try:
                    found = await self._scrape_market(model_number, market)
                    results.extend(found)
                    log.info("google_shopping.market_done", country=market["country"], found=len(found))
                    # Longer pause between markets
                    await asyncio.sleep(3.0)
                except Exception as e:
                    log.error("google_shopping.market_error", country=market["country"], error=str(e))

        return results

    async def _scrape_market(self, model_number: str, market: dict) -> list[ScrapedRetailer]:
        context = await self._new_context()
        page = await context.new_page()
        retailers: list[ScrapedRetailer] = []

        try:
            start = 0
            page_num = 0

            while page_num < MAX_PAGES_PER_MARKET:
                params = {
                    "tbm": "shop",
                    "q": model_number,
                    "gl": market["gl"],
                    "hl": market["hl"],
                }
                if start > 0:
                    params["start"] = str(start)

                url = f"https://www.google.com/search?{urlencode(params)}"
                await page.goto(url, timeout=settings.SCRAPE_TIMEOUT_MS)
                await self._random_delay()
                await self._human_scroll(page)

                # Check for CAPTCHA
                if await page.query_selector('form#captcha-form, [id="recaptcha"]'):
                    log.warning("google_shopping.captcha_detected", market=market["country"])
                    break

                page_retailers = await self._extract_shopping_results(page, market)
                if not page_retailers:
                    break

                retailers.extend(page_retailers)
                log.info("google_shopping.page_scraped",
                         country=market["country"], page=page_num + 1, found=len(page_retailers))

                # Check for "next page" link
                next_btn = await page.query_selector('a#pnnext, a[aria-label*="Next"]')
                if not next_btn:
                    break

                start += 40
                page_num += 1
                await self._random_delay()

        except Exception as e:
            log.error("google_shopping._scrape_market.error", market=market["country"], error=str(e))
        finally:
            await page.close()
            await context.close()

        return retailers

    async def _extract_shopping_results(self, page: Page, market: dict) -> list[ScrapedRetailer]:
        retailers: list[ScrapedRetailer] = []

        # Google Shopping result selectors (changes periodically — multiple fallbacks)
        result_selectors = [
            '.sh-dgr__content',
            'div[data-docid]',
            '.sh-pr__product-results-grid .g',
            '.pla-unit',
            '[data-hveid] .mnr-c',
        ]

        items = []
        for selector in result_selectors:
            items = await page.query_selector_all(selector)
            if items:
                break

        for item in items:
            try:
                # Merchant / shop name
                merchant_selectors = [
                    '.aULzUe',
                    '.E5ocAb',
                    '.IuHnof',
                    'div.sh-dlr__list-result a',
                    '.merchant-name',
                ]
                merchant = ""
                for sel in merchant_selectors:
                    el = await item.query_selector(sel)
                    if el:
                        merchant = (await el.inner_text()).strip()
                        break

                # Product URL — usually behind a click; try to extract from href
                link_el = await item.query_selector('a[href]')
                product_url = ""
                if link_el:
                    href = await link_el.get_attribute("href") or ""
                    # Google wraps URLs in /url?q= or /aclk? links
                    url_match = re.search(r'[?&](?:q|url|adurl)=([^&]+)', href)
                    if url_match:
                        from urllib.parse import unquote
                        product_url = unquote(url_match.group(1))
                    elif href.startswith("http"):
                        product_url = href

                # Price
                price_selectors = ['.a8Pemb', '.OFFNJ', '.T4OwTb', 'span[data-price]']
                price_text = ""
                for sel in price_selectors:
                    el = await item.query_selector(sel)
                    if el:
                        price_text = (await el.inner_text()).strip()
                        break
                price = _parse_price_international(price_text, market["currency"])

                if not merchant or not product_url:
                    continue

                domain = _extract_domain(product_url)
                if not domain:
                    continue

                retailers.append(ScrapedRetailer(
                    retailer_name=merchant,
                    retailer_domain=domain,
                    product_url=product_url,
                    country_code=market["country"],
                    currency=market["currency"],
                    price=price,
                    source=self.source_name,
                    raw_price_text=price_text,
                ))

            except Exception as e:
                log.debug("google_shopping.item_parse_error", error=str(e))
                continue

        return retailers


class GoogleOrganicScraper(BaseScraper):
    """
    Scrapes organic Google search results for shops without Shopping ads.
    Uses country-specific TLDs and localized buy keywords.
    Query: '"Model Number" site:*.cz' or '"Model Number" kaufen site:*.de'
    """
    source_name = "google_organic"

    async def discover(self, model_number: str, markets: list[str] | None = None) -> list[ScrapedRetailer]:
        target_markets = [m for m in EU_MARKETS if markets is None or m["country"] in markets]
        results: list[ScrapedRetailer] = []

        async with self:
            for market in target_markets:
                try:
                    found = await self._scrape_organic(model_number, market)
                    results.extend(found)
                    log.info("google_organic.done", country=market["country"], found=len(found))
                    await asyncio.sleep(3.0)
                except Exception as e:
                    log.error("google_organic.error", country=market["country"], error=str(e))

        return results

    async def _scrape_organic(self, model_number: str, market: dict) -> list[ScrapedRetailer]:
        context = await self._new_context()
        page = await context.new_page()
        retailers: list[ScrapedRetailer] = []

        try:
            # Use quoted model number + buy keyword
            query = f'"{model_number}" {market["buy_word"]}'
            params = {"q": query, "gl": market["gl"], "hl": market["hl"], "num": "100"}
            url = f"https://www.google.com/search?{urlencode(params)}"

            await page.goto(url, timeout=settings.SCRAPE_TIMEOUT_MS)
            await self._random_delay()
            await self._human_scroll(page)

            if await page.query_selector('form#captcha-form'):
                log.warning("google_organic.captcha", market=market["country"])
                return []

            # Extract organic search result URLs
            result_links = await page.query_selector_all('div.g a[href^="http"], div.yuRUbf a')
            seen_domains: set[str] = set()

            for link in result_links:
                try:
                    href = await link.get_attribute("href") or ""
                    if not href.startswith("http"):
                        continue
                    domain = _extract_domain(href)
                    if not domain or domain in seen_domains:
                        continue
                    # Filter out non-retail domains
                    if any(skip in domain for skip in ["google.", "youtube.", "facebook.", "wikipedia.", "amazon."]):
                        continue
                    seen_domains.add(domain)

                    # Get page title for retailer name
                    title_el = await link.query_selector('h3')
                    title = (await title_el.inner_text()).strip() if title_el else domain

                    retailers.append(ScrapedRetailer(
                        retailer_name=title[:100],
                        retailer_domain=domain,
                        product_url=href,
                        country_code=market["country"],
                        currency=market["currency"],
                        price=None,  # requires individual page scrape
                        source=self.source_name,
                    ))
                except Exception:
                    continue

        except Exception as e:
            log.error("google_organic._scrape", error=str(e))
        finally:
            await page.close()
            await context.close()

        return retailers


def _parse_price_international(text: str, currency: str) -> float | None:
    if not text:
        return None
    # Remove currency symbols and non-numeric chars except , and .
    cleaned = re.sub(r'[^\d,\.\s]', '', text).strip()
    cleaned = re.sub(r'\s+', '', cleaned)
    if not cleaned:
        return None
    # European decimal comma
    if ',' in cleaned and '.' not in cleaned:
        cleaned = cleaned.replace(',', '.')
    elif ',' in cleaned and '.' in cleaned:
        # e.g. 1.234,56 → 1234.56
        cleaned = cleaned.replace('.', '').replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_domain(url: str) -> str:
    match = re.match(r'https?://(?:www\.)?([^/?#]+)', url)
    return match.group(1) if match else ""


