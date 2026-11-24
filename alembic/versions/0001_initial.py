# -*- coding: utf-8 -*-
"""Начальная схема: реестр кампаний, потоки, привязки офферов, кэш каталога.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("alias", sa.String(64), nullable=True),
        sa.Column("domain_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("traffic_source_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "streams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(32), nullable=True),
        sa.Column("schema", sa.String(32), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("is_offer_stream", sa.Boolean(), nullable=True),
    )
    op.create_table(
        "offer_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stream_id", sa.Integer(), sa.ForeignKey("streams.id"), index=True),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("share", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
    )
    op.create_table(
        "offer_cache",
        sa.Column("offer_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("state", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("offer_cache")
    op.drop_table("offer_bindings")
    op.drop_table("streams")
    op.drop_table("campaigns")
