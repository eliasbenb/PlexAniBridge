"""TVDB Mappings

Revision ID: c5581ec025a7
Revises: ddbadb26481f
Create Date: 2025-02-17 14:29:10.113697

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # added

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c5581ec025a7'
down_revision: Union[str, None] = 'ddbadb26481f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('animap', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tvdb_mappings', sa.JSON(none_as_null=True), nullable=True))
        batch_op.create_index(batch_op.f('ix_animap_tvdb_mappings'), ['tvdb_mappings'], unique=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('animap', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_animap_tvdb_mappings'))
        batch_op.drop_column('tvdb_mappings')

    # ### end Alembic commands ###
