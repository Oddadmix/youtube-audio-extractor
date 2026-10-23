"""add_error_message_to_jobs

Revision ID: c4f1d2e3a5b6
Revises: 974a6696c192
Create Date: 2026-10-23 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f1d2e3a5b6'
down_revision: Union[str, None] = '974a6696c192'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('error_message', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('jobs', 'error_message')
