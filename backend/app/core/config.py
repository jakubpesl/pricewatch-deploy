from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "dev-secret-change-in-production"
    ENVIRONMENT: str = "development"
    OLLAMA_URL: str = "http://localhost:11434"

    # Scraping
    SCRAPE_DELAY_MIN: float = 2.0
    SCRAPE_DELAY_MAX: float = 5.0
    SCRAPE_TIMEOUT_MS: int = 30000
    HEADLESS: bool = True

    # Frontend URL for CORS (set to Vercel URL in production)
    FRONTEND_URL: str = "http://localhost:3000"


settings = Settings()
