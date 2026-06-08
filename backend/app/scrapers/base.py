import asyncio
import random
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    _PLAYWRIGHT = True
except ImportError:
    _PLAYWRIGHT = False
    Browser = BrowserContext = Page = object  # type: ignore[assignment,misc]
from fake_useragent import UserAgent
from app.core.config import settings
import structlog

log = structlog.get_logger()
ua = UserAgent()


@dataclass
class ScrapedRetailer:
    retailer_name: str
    retailer_domain: str
    product_url: str
    country_code: str
    currency: str
    price: float | None
    original_price: float | None = None
    in_stock: bool | None = None
    rating: float | None = None
    review_count: int | None = None
    image_url: str | None = None
    source: str = ""
    raw_price_text: str = ""
    extra: dict = field(default_factory=dict)


class BaseScraper(ABC):
    """Base class for all scrapers. Manages Playwright lifecycle and stealth settings."""

    source_name: str = "unknown"

    def __init__(self):
        self._browser: Browser | None = None
        self._playwright = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--window-size=1366,768",
            ],
        )
        return self

    async def __aexit__(self, *args):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _new_context(self) -> BrowserContext:
        user_agent = ua.random
        context = await self._browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="Europe/Berlin",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "DNT": "1",
            },
            java_script_enabled=True,
        )
        # Inject stealth JS to evade basic bot detection
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)
        return context

    async def _random_delay(self):
        delay = random.uniform(settings.SCRAPE_DELAY_MIN, settings.SCRAPE_DELAY_MAX)
        await asyncio.sleep(delay)

    async def _human_scroll(self, page: Page):
        """Simulate human-like scrolling."""
        for _ in range(random.randint(2, 5)):
            await page.evaluate(f"window.scrollBy(0, {random.randint(200, 600)})")
            await asyncio.sleep(random.uniform(0.3, 0.8))

    @abstractmethod
    async def discover(self, model_number: str) -> list[ScrapedRetailer]:
        """Discover all retailers for a model number."""
        ...

    async def scrape_price(self, url: str, country_code: str) -> ScrapedRetailer | None:
        """Scrape current price from a known product URL."""
        return None
