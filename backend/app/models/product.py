from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, Integer, Text, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class Product(Base):
    """A unique product identified by model number."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_number: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(512))
    brand: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(255))
    ean: Mapped[str | None] = mapped_column(String(50), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(1024))
    # Embedding for AI matching (384-dim all-MiniLM-L6-v2)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    meta: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    retailers: Mapped[list["ProductRetailer"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    monitors: Mapped[list["Monitor"]] = relationship(back_populates="product")  # noqa: F821


class ProductRetailer(Base):
    """A specific product listing at a specific retailer in a specific country."""
    __tablename__ = "product_retailers"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    retailer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    retailer_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)  # ISO 3166-1 alpha-2
    product_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # ISO 4217
    current_price: Mapped[float | None] = mapped_column(Float)
    original_price: Mapped[float | None] = mapped_column(Float)  # before discount
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    stock_level: Mapped[str | None] = mapped_column(String(50))  # "high" | "low" | "out"
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column(Integer)
    screenshot_url: Mapped[str | None] = mapped_column(String(1024))
    source: Mapped[str] = mapped_column(String(100), nullable=False)  # "heureka" | "google_shopping" | etc.
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    product: Mapped["Product"] = relationship(back_populates="retailers")
    price_history: Mapped[list["PricePoint"]] = relationship(back_populates="retailer", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_product_retailers_product_domain_country", "product_id", "retailer_domain", "country_code"),
    )


class PricePoint(Base):
    """Time-series price observations. Converted to TimescaleDB hypertable via migration."""
    __tablename__ = "price_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    retailer_id: Mapped[int] = mapped_column(ForeignKey("product_retailers.id", ondelete="CASCADE"), index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    original_price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    retailer: Mapped["ProductRetailer"] = relationship(back_populates="price_history")

    __table_args__ = (
        Index("ix_price_points_retailer_observed", "retailer_id", "observed_at"),
    )
