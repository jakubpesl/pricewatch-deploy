"""
Lightweight httpx-based scrapers — no Playwright, no browser, runs on 512MB RAM.
Uses JSON-LD structured data extraction + BeautifulSoup HTML fallback.
"""
import asyncio
import json
import re
import random
from urllib.parse import quote_plus, urlparse
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from app.scrapers.base import ScrapedRetailer
import structlog

log = structlog.get_logger()
ua = UserAgent()

TIMEOUT = 15  # seconds per request
DELAY = (0.5, 1.5)  # random delay between requests


def _headers() -> dict:
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
    }


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    await asyncio.sleep(random.uniform(*DELAY))
    return await client.get(url, headers=_headers(), follow_redirects=True, timeout=TIMEOUT)


def _extract_jsonld(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict):
                results.append(data)
        except Exception:
            pass
    return results


def _parse_price(text: str) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d,.]", "", str(text).replace("\xa0", "").replace(" ", ""))
    cleaned = cleaned.replace(",", ".")
    # Handle "1.234.56" → take last decimal group
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = "".join(parts[:-1]).replace(".", "") + "." + parts[-1]
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


def _domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "").strip()


# ── Heureka CZ / SK ──────────────────────────────────────────────────────────

HEUREKA_SITES = [
    {"base": "https://www.heureka.cz", "country": "CZ", "currency": "CZK"},
    {"base": "https://www.heureka.sk", "country": "SK", "currency": "EUR"},
]


class HeurekaHttpxScraper:
    source_name = "heureka"

    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        results: list[ScrapedRetailer] = []
        async with httpx.AsyncClient() as client:
            for site in HEUREKA_SITES:
                try:
                    found = await self._scrape_site(client, model_number, site)
                    results.extend(found)
                    log.info("heureka_httpx.done", site=site["base"], found=len(found))
                except Exception as e:
                    log.error("heureka_httpx.error", site=site["base"], error=str(e))
        return results

    async def _scrape_site(self, client: httpx.AsyncClient, model_number: str, site: dict) -> list[ScrapedRetailer]:
        # Search
        search_url = f"{site['base']}/direct/?h[fraze]={quote_plus(model_number)}"
        resp = await _get(client, search_url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Find product page link
        product_url = self._find_product_link(soup, site["base"], model_number)
        if not product_url:
            return []

        # Fetch product page
        resp = await _get(client, product_url)
        return self._extract_offers(resp.text, site, product_url)

    def _find_product_link(self, soup: BeautifulSoup, base: str, model: str) -> str | None:
        selectors = [
            "a.product-name__link", "a.ProductCard-link",
            ".ProductCard a", "h2.ProductCard-title a",
            "a[data-testid='product-link']",
        ]
        for sel in selectors:
            for tag in soup.select(sel):
                href = tag.get("href", "")
                if href:
                    return href if href.startswith("http") else base + href
        # Fallback: first link containing model keyword
        for a in soup.find_all("a", href=True):
            if any(w.lower() in (a.get_text() + a["href"]).lower() for w in model.split()[:2]):
                href = a["href"]
                return href if href.startswith("http") else base + href
        return None

    def _extract_offers(self, html: str, site: dict, product_url: str) -> list[ScrapedRetailer]:
        results: list[ScrapedRetailer] = []

        # Try JSON-LD first
        for ld in _extract_jsonld(html):
            if ld.get("@type") == "Product":
                offers = ld.get("offers", [])
                if isinstance(offers, dict):
                    offers = [offers]
                for offer in offers:
                    price = _parse_price(offer.get("price"))
                    if not price:
                        continue
                    url = offer.get("url", product_url)
                    seller = offer.get("seller", {})
                    name = seller.get("name", "") if isinstance(seller, dict) else str(seller)
                    dom = _domain(url) or _domain(product_url)
                    results.append(ScrapedRetailer(
                        retailer_name=name or dom,
                        retailer_domain=dom,
                        product_url=url,
                        country_code=site["country"],
                        currency=site["currency"],
                        price=price,
                        in_stock=offer.get("availability", "").lower().endswith("stock"),
                        source="heureka",
                    ))

        # HTML fallback: shop rows
        if not results:
            soup = BeautifulSoup(html, "lxml")
            for row in soup.select(".ShopOffer, .offer-row, [class*='shopOffer'], [class*='ShopList-item']"):
                name_tag = row.select_one("[class*='shop-name'], [class*='shopName'], .shop a")
                price_tag = row.select_one("[class*='price'], .Price")
                link_tag = row.select_one("a[href]")
                if not link_tag:
                    continue
                href = link_tag.get("href", "")
                price = _parse_price(price_tag.get_text() if price_tag else "")
                name = name_tag.get_text(strip=True) if name_tag else ""
                dom = _domain(href) if href.startswith("http") else ""
                if dom:
                    results.append(ScrapedRetailer(
                        retailer_name=name or dom,
                        retailer_domain=dom,
                        product_url=href,
                        country_code=site["country"],
                        currency=site["currency"],
                        price=price,
                        source="heureka",
                    ))

        return results


# ── Zbozi.cz ─────────────────────────────────────────────────────────────────

class ZboziHttpxScraper:
    source_name = "zbozi"

    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        results: list[ScrapedRetailer] = []
        async with httpx.AsyncClient() as client:
            try:
                url = f"https://www.zbozi.cz/hledani/?q={quote_plus(model_number)}"
                resp = await _get(client, url)
                soup = BeautifulSoup(resp.text, "lxml")

                product_link = None
                for a in soup.select("a.ProductCard-link, .productCard-title, h2 a, h3 a"):
                    href = a.get("href", "")
                    if href and "zbozi.cz" in href:
                        product_link = href
                        break

                if not product_link:
                    return []

                resp = await _get(client, product_link)
                results = self._parse_offers(resp.text, product_link)
            except Exception as e:
                log.error("zbozi_httpx.error", error=str(e))
        return results

    def _parse_offers(self, html: str, product_url: str) -> list[ScrapedRetailer]:
        results: list[ScrapedRetailer] = []
        for ld in _extract_jsonld(html):
            if ld.get("@type") == "Product":
                offers = ld.get("offers", [])
                if isinstance(offers, dict):
                    offers = [offers]
                for offer in offers:
                    price = _parse_price(offer.get("price"))
                    if not price:
                        continue
                    url = offer.get("url", product_url)
                    seller = offer.get("seller", {})
                    name = seller.get("name", "") if isinstance(seller, dict) else ""
                    dom = _domain(url)
                    results.append(ScrapedRetailer(
                        retailer_name=name or dom,
                        retailer_domain=dom,
                        product_url=url,
                        country_code="CZ",
                        currency="CZK",
                        price=price,
                        source="zbozi",
                    ))
        return results


# ── Geizhals AT/DE ────────────────────────────────────────────────────────────

GEIZHALS_SITES = [
    {"base": "https://geizhals.at",  "country": "AT", "currency": "EUR"},
    {"base": "https://geizhals.de",  "country": "DE", "currency": "EUR"},
]


class GeizhalsHttpxScraper:
    source_name = "geizhals"

    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        results: list[ScrapedRetailer] = []
        async with httpx.AsyncClient() as client:
            for site in GEIZHALS_SITES:
                try:
                    url = f"{site['base']}/?fs={quote_plus(model_number)}"
                    resp = await _get(client, url)
                    found = self._parse(resp.text, site)
                    results.extend(found)
                    log.info("geizhals_httpx.done", site=site["base"], found=len(found))
                except Exception as e:
                    log.error("geizhals_httpx.error", site=site["base"], error=str(e))
        return results

    def _parse(self, html: str, site: dict) -> list[ScrapedRetailer]:
        results: list[ScrapedRetailer] = []
        soup = BeautifulSoup(html, "lxml")

        for ld in _extract_jsonld(html):
            if ld.get("@type") == "Product":
                offers = ld.get("offers", [])
                if isinstance(offers, dict):
                    offers = [offers]
                for offer in offers:
                    price = _parse_price(offer.get("price"))
                    if not price:
                        continue
                    url = offer.get("url", site["base"])
                    seller = offer.get("seller", {})
                    name = seller.get("name", "") if isinstance(seller, dict) else ""
                    dom = _domain(url)
                    results.append(ScrapedRetailer(
                        retailer_name=name or dom,
                        retailer_domain=dom,
                        product_url=url,
                        country_code=site["country"],
                        currency=site["currency"],
                        price=price,
                        source="geizhals",
                    ))

        # HTML fallback
        if not results:
            for row in soup.select("tr.offer, .offer-list-item, [class*='offer']"):
                shop = row.select_one("a.merchant, .shop-name, a[class*='shop']")
                price_el = row.select_one(".price, [class*='price']")
                link = row.select_one("a[href]")
                if not link:
                    continue
                price = _parse_price(price_el.get_text() if price_el else "")
                href = link.get("href", "")
                href = href if href.startswith("http") else site["base"] + href
                dom = _domain(href)
                if dom and dom != _domain(site["base"]):
                    results.append(ScrapedRetailer(
                        retailer_name=shop.get_text(strip=True) if shop else dom,
                        retailer_domain=dom,
                        product_url=href,
                        country_code=site["country"],
                        currency=site["currency"],
                        price=price,
                        source="geizhals",
                    ))
        return results


# ── Ceneo PL ─────────────────────────────────────────────────────────────────

class CeneoHttpxScraper:
    source_name = "ceneo"

    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        results: list[ScrapedRetailer] = []
        async with httpx.AsyncClient() as client:
            try:
                url = f"https://www.ceneo.pl/szukaj-{quote_plus(model_number)}"
                resp = await _get(client, url)
                soup = BeautifulSoup(resp.text, "lxml")

                product_link = None
                for a in soup.select("a.go-to-product, .cat-prod-row a, .product-name a"):
                    href = a.get("href", "")
                    if href:
                        product_link = href if href.startswith("http") else "https://www.ceneo.pl" + href
                        break

                if not product_link:
                    return []

                resp = await _get(client, product_link)
                results = self._parse(resp.text)
            except Exception as e:
                log.error("ceneo_httpx.error", error=str(e))
        return results

    def _parse(self, html: str) -> list[ScrapedRetailer]:
        results: list[ScrapedRetailer] = []
        for ld in _extract_jsonld(html):
            if ld.get("@type") == "Product":
                offers = ld.get("offers", [])
                if isinstance(offers, dict):
                    offers = [offers]
                for offer in offers:
                    price = _parse_price(offer.get("price"))
                    if not price:
                        continue
                    url = offer.get("url", "https://www.ceneo.pl")
                    seller = offer.get("seller", {})
                    name = seller.get("name", "") if isinstance(seller, dict) else ""
                    dom = _domain(url)
                    results.append(ScrapedRetailer(
                        retailer_name=name or dom,
                        retailer_domain=dom,
                        product_url=url,
                        country_code="PL",
                        currency="PLN",
                        price=price,
                        source="ceneo",
                    ))
        return results


# ── Placeholder for scrapers that need JS (return empty quickly) ──────────────

class NoopScraper:
    def __init__(self, name: str):
        self.source_name = name

    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        return []
