"""
Drop password_hash column from users table.

Revision ID: 0003
Revises:     0002
Create Date: 2026-06-28

Background:
    Post-Pilot uses magic-link email authentication only. The password_hash
    column was part of the original schema but is never written or read by
    any live code path. Keeping it creates risk (implies password auth exists)
    and schema confusion.

Safety:
    - Verified no code references password_hash before applying.
      Search: grep -r "password_hash" . --include="*.py"
      Expected result: zero matches (excluding this file and alembic history).
    - This migration is irreversible. Back up before applying to production.
    - Uses batch_alter_table for SQLite compatibility (SQLite does not support
      DROP COLUMN directly; batch mode rewrites the table).

Applying:
    alembic upgrade head

Verify after:
    sqlite3 postpilot.db ".schema users"   # local
    -- or in Supabase SQL editor:
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'password_hash';
    -- should return 0 rows
"""

from alembic import op
import sqlalchemy as sa

revision      = '0003'
down_revision = '0002'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # batch_alter_table handles both SQLite (which rewrites the table)
    # and PostgreSQL (which issues ALTER TABLE ... DROP COLUMN directly).
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('password_hash')


def downgrade() -> None:
    # Restore the column as nullable (original was NOT NULL but data is gone).
    # This is a structural restore only -- no data is recovered.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('password_hash', sa.Text(), nullable=True)
        )
