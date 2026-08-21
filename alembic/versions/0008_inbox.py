"""
Add inbox_items table for social comment inbox and auto-reply poller.

Revision ID: 0008
Revises:     0006
Create Date: 2026-08-19

inbox_items
    One row per ingested comment from Facebook, Instagram, etc.
    Stores comment metadata, sentiment analysis, AI draft response,
    moderation status, and reply history.
"""

from alembic import op
import sqlalchemy as sa

revision      = '0008'
down_revision = '0006'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        'inbox_items',
        sa.Column('id',                  sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id',             sa.Text(),    nullable=False),
        sa.Column('platform',            sa.Text(),    nullable=False),   # 'fb' | 'ig'
        sa.Column('platform_post_id',    sa.Text(),    nullable=True),
        sa.Column('platform_comment_id', sa.Text(),    nullable=False),
        sa.Column('author_id',           sa.Text(),    nullable=True),
        sa.Column('author_name',         sa.Text(),    nullable=True),
        sa.Column('comment_text',        sa.Text(),    nullable=False),
        sa.Column('comment_time',        sa.Text(),    nullable=True),
        sa.Column('post_context',        sa.Text(),    nullable=True),
        sa.Column('sentiment',           sa.Text(),    nullable=True, server_default='neutral'),
        sa.Column('ai_draft_reply',      sa.Text(),    nullable=True),
        sa.Column('final_reply',         sa.Text(),    nullable=True),
        sa.Column('status',              sa.Text(),    nullable=True, server_default='pending'),
        sa.Column('auto_replied',        sa.Integer(), nullable=True, server_default='0'),
        sa.Column('replied_at',          sa.Integer(), nullable=True),
        sa.Column('hidden_at',           sa.Integer(), nullable=True),
        sa.Column('created_at',          sa.Integer(), nullable=True,
                  server_default=sa.text("(strftime('%s','now'))")),
        sa.Column('updated_at',          sa.Integer(), nullable=True,
                  server_default=sa.text("(strftime('%s','now'))")),
        sa.UniqueConstraint('platform', 'platform_comment_id', name='uq_inbox_platform_comment'),
    )
    op.create_index('idx_inbox_user',              'inbox_items', ['user_id'])
    op.create_index('idx_inbox_user_status',       'inbox_items', ['user_id', 'status'])
    op.create_index('idx_inbox_user_sentiment',    'inbox_items', ['user_id', 'sentiment'])
    op.create_index('idx_inbox_platform_comment',  'inbox_items', ['platform', 'platform_comment_id'])


def downgrade() -> None:
    op.drop_index('idx_inbox_platform_comment',  table_name='inbox_items')
    op.drop_index('idx_inbox_user_sentiment',    table_name='inbox_items')
    op.drop_index('idx_inbox_user_status',       table_name='inbox_items')
    op.drop_index('idx_inbox_user',              table_name='inbox_items')
    op.drop_table('inbox_items')
