"""Initial schema with TimescaleDB hypertable

Revision ID: 001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_verified", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # products
    op.create_table(
        "products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("model_number", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(512)),
        sa.Column("brand", sa.String(255)),
        sa.Column("category", sa.String(255)),
        sa.Column("ean", sa.String(50)),
        sa.Column("description", sa.Text),
        sa.Column("image_url", sa.String(1024)),
        sa.Column("embedding", Vector(384)),
        sa.Column("meta", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_products_model_number", "products", ["model_number"])
    op.create_index("ix_products_ean", "products", ["ean"])

    # product_retailers
    op.create_table(
        "product_retailers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("retailer_name", sa.String(255), nullable=False),
        sa.Column("retailer_domain", sa.String(255), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("product_url", sa.String(2048), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("current_price", sa.Float),
        sa.Column("original_price", sa.Float),
        sa.Column("in_stock", sa.Boolean),
        sa.Column("stock_level", sa.String(50)),
        sa.Column("rating", sa.Float),
        sa.Column("review_count", sa.Integer),
        sa.Column("screenshot_url", sa.String(1024)),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_product_retailers_product_id", "product_retailers", ["product_id"])
    op.create_index("ix_product_retailers_domain", "product_retailers", ["retailer_domain"])
    op.create_index(
        "ix_product_retailers_product_domain_country",
        "product_retailers",
        ["product_id", "retailer_domain", "country_code"],
        unique=True,
    )

    # price_points (TimescaleDB hypertable)
    op.create_table(
        "price_points",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("retailer_id", sa.Integer, sa.ForeignKey("product_retailers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("original_price", sa.Float),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("in_stock", sa.Boolean),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_price_points_retailer_observed", "price_points", ["retailer_id", "observed_at"])
    # Convert to TimescaleDB hypertable (partitioned by time)
    op.execute("SELECT create_hypertable('price_points', 'observed_at', if_not_exists => TRUE)")

    # monitors
    op.create_table(
        "monitors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("retailer_ids", JSONB),
        sa.Column("alert_on_price_drop", sa.Boolean, default=True),
        sa.Column("alert_on_price_increase", sa.Boolean, default=False),
        sa.Column("alert_on_stock_change", sa.Boolean, default=True),
        sa.Column("alert_on_new_retailer", sa.Boolean, default=True),
        sa.Column("target_price", sa.Float),
        sa.Column("price_change_threshold_pct", sa.Float, default=2.0),
        sa.Column("check_interval_hours", sa.Integer, default=6),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("monitor_id", sa.Integer, sa.ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("retailer_id", sa.Integer, sa.ForeignKey("product_retailers.id", ondelete="SET NULL")),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("old_price", sa.Float),
        sa.Column("new_price", sa.Float),
        sa.Column("price_change_pct", sa.Float),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("is_read", sa.Boolean, default=False),
        sa.Column("email_sent", sa.Boolean, default=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alerts_triggered_at", "alerts", ["triggered_at"])

    # discovery_jobs
    op.create_table(
        "discovery_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("model_number", sa.String(255), nullable=False),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("sources_requested", JSONB),
        sa.Column("sources_completed", JSONB),
        sa.Column("retailers_found", sa.Integer, default=0),
        sa.Column("error_message", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # scrape_jobs
    op.create_table(
        "scrape_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("retailer_id", sa.Integer, sa.ForeignKey("product_retailers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("price_found", sa.String(50)),
        sa.Column("error_message", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("scrape_jobs")
    op.drop_table("discovery_jobs")
    op.drop_table("alerts")
    op.drop_table("monitors")
    op.drop_table("price_points")
    op.drop_table("product_retailers")
    op.drop_table("products")
    op.drop_table("users")
