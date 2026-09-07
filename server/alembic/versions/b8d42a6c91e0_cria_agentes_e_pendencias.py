"""cria agentes e pendencias

Revision ID: b8d42a6c91e0
Revises: f3a91c07b2d4
Create Date: 2026-09-07 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d42a6c91e0'
down_revision: Union[str, Sequence[str], None] = 'f3a91c07b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('agentes',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pendencias',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('agente_id', sa.String(length=64), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('prioridade', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['agente_id'], ['agentes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pendencias', schema=None) as batch_op:
        batch_op.create_index('ix_pendencias_agente_id', ['agente_id'], unique=False)
        batch_op.create_index(
            'ix_pendencias_prioridade_created_at',
            ['prioridade', 'created_at'],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('pendencias', schema=None) as batch_op:
        batch_op.drop_index('ix_pendencias_prioridade_created_at')
        batch_op.drop_index('ix_pendencias_agente_id')

    op.drop_table('pendencias')
    op.drop_table('agentes')
