"""
Add platform_settings table -- per-user platform toggle switches.

Revision ID: 0002
Revises:     0001
Create Date: 2026-06-22

This table is read by:
  blueprints/api.py  _get_enabled_platforms()   -- filters which platforms
                                                    are adapted and published
  blueprints/api.py  api_save_platform_settings() -- writes user toggle state

Schema:
    platform_settings
        user_id   TEXT  -- FK to users.id
        platform  TEXT  -- short platform key: fb, ig, tt, yt, yts, li, tw, pi, gb, web
        enabled   INTEGER  -- 1 = on, 0 = off
        PRIMARY KEY (user_id, platform)

Default behaviour:
    If no row exists for a user+platform, the app treats it as enabled=1
    (opt-in by default once connected). Rows are only written when the user
    explicitly changes a toggle in Settings.

Applying to an existing database:
    alembic upgrade head
"""

from alembic import op
import sqlalchemy as sa

revision      = '0002'
down_revision = '0001'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        'platform_settings',
        sa.Column('user_id',  sa.Text(),    nullable=False),
        sa.Column('platform', sa.Text(),    nullable=False),
        sa.Column('enabled',  sa.Integer(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('user_id', 'platform', name='pk_platform_settings'),
    )
    op.create_index('idx_platform_settings_user', 'platform_settings', ['user_id'])


def downgrade() -> None:
    op.drop_index('idx_platform_settings_user', table_name='platform_settings')
    op.drop_table('platform_settings')
