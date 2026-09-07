"""cria messages_uso

Revision ID: f3a91c07b2d4
Revises: de5d29372cf2
Create Date: 2026-09-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a91c07b2d4'
down_revision: Union[str, Sequence[str], None] = 'de5d29372cf2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('messages_uso',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('message_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('message_id')
    )
    with op.batch_alter_table('messages_uso', schema=None) as batch_op:
        batch_op.create_index('ix_messages_uso_created_at', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('messages_uso', schema=None) as batch_op:
        batch_op.drop_index('ix_messages_uso_created_at')

    op.drop_table('messages_uso')
