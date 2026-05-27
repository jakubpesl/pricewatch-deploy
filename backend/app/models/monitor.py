from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, Integer, Text, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base
import enum


class AlertType(str, enum.Enum):
    PRICE_DROP = "price_drop"
    PRICE_INCREASE = "price_increase"
    BACK_IN_STOCK = "back_in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PRICE_BELOW_TARGET = "price_below_target"
    NEW_RETAILER_FOUND = "new_retailer_found"


class Monitor(Base):
    """User-configured monitoring rule for a product."""
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Which retailers to monitor (None = all)
    retailer_ids: Mapped[list[int] | None] = mapped_column(JSONB)
    # Alert conditions
    alert_on_price_drop: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_price_increase: Mapped[bool] = mapped_column(Boolean, default=False)
    alert_on_stock_change: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_new_retailer: Mapped[bool] = mapped_column(Boolean, default=True)
    target_price: Mapped[float | None] = mapped_column(Float)  # alert when price drops below this
    price_change_threshold_pct: Mapped[float] = mapped_column(Float, default=2.0)  # min % change to alert
    # Schedule
    check_interval_hours: Mapped[int] = mapped_column(Integer, default=6)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="monitors")  # noqa: F821
    product: Mapped["Product"] = relationship(back_populates="monitors")  # noqa: F821
    alerts: Mapped[list["Alert"]] = relationship(back_populates="monitor", cascade="all, delete-orphan")


class Alert(Base):
    """A triggered alert event."""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), index=True)
    retailer_id: Mapped[int | None] = mapped_column(ForeignKey("product_retailers.id", ondelete="SET NULL"))
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType), nullable=False)
    old_price: Mapped[float | None] = mapped_column(Float)
    new_price: Mapped[float | None] = mapped_column(Float)
    price_change_pct: Mapped[float | None] = mapped_column(Float)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    monitor: Mapped["Monitor"] = relationship(back_populates="alerts")
