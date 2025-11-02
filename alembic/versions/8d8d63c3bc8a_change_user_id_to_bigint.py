"""change_user_id_to_bigint

Revision ID: 8d8d63c3bc8a
Revises: add_audit_logs
Create Date: 2025-11-02 16:29:41.789549

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d8d63c3bc8a'
down_revision: Union[str, Sequence[str], None] = 'add_audit_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # For MySQL with auto-increment primary key, we need to use raw SQL
    # Change user_id to BIGINT in users table
    op.execute('ALTER TABLE users MODIFY COLUMN user_id BIGINT NOT NULL AUTO_INCREMENT')

    # Change user_id to BIGINT in audit_logs table
    op.alter_column('audit_logs', 'user_id', type_=sa.BigInteger(), existing_type=sa.Integer())


def downgrade() -> None:
    """Downgrade schema."""
    # Revert user_id back to Integer in users table
    op.alter_column('users', 'user_id', type_=sa.Integer(), existing_type=sa.BigInteger())
    # Revert user_id back to Integer in audit_logs table
    op.alter_column('audit_logs', 'user_id', type_=sa.Integer(), existing_type=sa.BigInteger())
