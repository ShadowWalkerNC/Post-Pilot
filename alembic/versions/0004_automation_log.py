"""
Add automation_log table -- audit trail for AutomationAgent decisions.

Revision ID: 0004
Revises:     0003
Create Date: 2026-06-28

This table is written by modules/automation_agent.py every time the agent
creates a scheduled post. It records the full decision context so that:
  - You can audit exactly why a post was generated.
  - You can debug generation quality (tone, keywords, master caption).
  - You can build a dashboard view of agent activity.

Schema:
    automation_log
        id             INTEGER  PRIMARY KEY AUTOINCREMENT
        user_id        TEXT     -- FK to users.id
        post_id        INTEGER  -- FK to post_history.id (the scheduled post)
        content_type   TEXT     -- 'daily_special' | 'location' | 'general'
        tone           TEXT     -- tone used for generation
        keywords       TEXT     -- JSON array of keywords passed to AI
        master_caption TEXT     -- the platform-neutral master caption generated
        scheduled_at   INTEGER  -- Unix timestamp the post is scheduled for
        created_at     INTEGER  -- Unix timestamp this log row was created

Applying:
    alembic upgrade head
"""

from alembic import op
import sqlalchemy as sa

revision      = '0004'
down_revision = '0003'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        'automation_log',
        sa.Column('id',             sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id',        sa.Text(),    nullable=False),
        sa.Column('post_id',        sa.Integer(), nullable=True),
        sa.Column('content_type',   sa.Text(),    nullable=False),
        sa.Column('tone',           sa.Text(),    nullable=True),
        sa.Column('keywords',       sa.Text(),    nullable=True),
        sa.Column('master_caption', sa.Text(),    nullable=True),
        sa.Column('scheduled_at',   sa.Integer(), nullable=True),
        sa.Column('created_at',     sa.Integer(), nullable=True,
                  server_default=sa.text("(strftime('%s','now'))")),
    )
    op.create_index('idx_automation_log_user',    'automation_log', ['user_id'])
    op.create_index('idx_automation_log_post',    'automation_log', ['post_id'])
    op.create_index('idx_automation_log_created', 'automation_log', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_automation_log_created', table_name='automation_log')
    op.drop_index('idx_automation_log_post',    table_name='automation_log')
    op.drop_index('idx_automation_log_user',    table_name='automation_log')
    op.drop_table('automation_log')
