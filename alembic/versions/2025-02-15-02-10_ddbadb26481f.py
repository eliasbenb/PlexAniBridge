"""AniMap v2 schema migration

Revision ID: ddbadb26481f
Revises: 424fe94c2c03
Create Date: 2025-02-15 02:10:50.182654

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ddbadb26481f'
down_revision: Union[str, None] = '424fe94c2c03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('animap', schema=None) as batch_op:
        batch_op.drop_column('tvdb_epoffset')
        batch_op.drop_column('tvdb_season')

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('animap', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tvdb_season', sa.INTEGER(), nullable=True))
        batch_op.add_column(sa.Column('tvdb_epoffset', sa.INTEGER(), nullable=True))

    # ### end Alembic commands ###
