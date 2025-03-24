"""Delete unutilized indexes

Revision ID: e89ead9178d7
Revises: 6b471e97e780
Create Date: 2025-03-24 02:37:18.107721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel # added


# revision identifiers, used by Alembic.
revision: str = 'e89ead9178d7'
down_revision: Union[str, None] = '6b471e97e780'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('animap', schema=None) as batch_op:
        batch_op.drop_index('ix_animap_anidb_id')
        batch_op.drop_index('ix_animap_mal_id')
        batch_op.drop_index('ix_animap_tvdb_mappings')

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('animap', schema=None) as batch_op:
        batch_op.create_index('ix_animap_tvdb_mappings', ['tvdb_mappings'], unique=False)
        batch_op.create_index('ix_animap_mal_id', ['mal_id'], unique=False)
        batch_op.create_index('ix_animap_anidb_id', ['anidb_id'], unique=False)

    # ### end Alembic commands ###
