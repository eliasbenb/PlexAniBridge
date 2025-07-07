"""Drop AniDB unique index

Revision ID: 424fe94c2c03
Revises: b2ad27e14048
Create Date: 2025-02-04 01:57:53.836952

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "424fe94c2c03"
down_revision: Union[str, None] = "b2ad27e14048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_animap_anidb_id", table_name="animap")
    op.create_index("ix_animap_anidb_id", "animap", ["anidb_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_animap_anidb_id", table_name="animap")
    op.create_index("ix_animap_anidb_id", "animap", ["anidb_id"], unique=True)
