"""Migration to the PlexAniBridge mapping database

Revision ID: b2ad27e14048
Revises: 6e710e6677c0
Create Date: 2025-01-15 15:52:56.167462

"""

import sqlalchemy as sa
from sqlmodel import JSON

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2ad27e14048"
down_revision = "6e710e6677c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite doesn't support altering primary keys directly.
    # Workaround: Create a new table with the updated schema, copy data, and replace the old table.

    # Drop indexes explicitly
    with op.batch_alter_table("animap", schema=None) as batch_op:
        batch_op.drop_index("ix_animap_anilist_id")
        batch_op.drop_index("ix_animap_imdb_id")
        batch_op.drop_index("ix_animap_mal_id")
        batch_op.drop_index("ix_animap_tmdb_movie_id")
        batch_op.drop_index("ix_animap_tmdb_show_id")
        batch_op.drop_index("ix_animap_tvdb_id")

    # Create a new table with the desired schema and primary key
    op.create_table(
        "animap_new",
        sa.Column(
            "anidb_id", sa.Integer, primary_key=True, nullable=False
        ),  # New primary key
        sa.Column("anilist_id", sa.Integer, nullable=True),
        sa.Column("imdb_id", JSON(none_as_null=True), nullable=True),
        sa.Column("mal_id", JSON(none_as_null=True), nullable=True),
        sa.Column("tmdb_movie_id", JSON(none_as_null=True), nullable=True),
        sa.Column("tmdb_show_id", JSON(none_as_null=True), nullable=True),
        sa.Column("tvdb_id", sa.Integer, nullable=True),
        sa.Column("tvdb_epoffset", sa.Integer, nullable=True),
        sa.Column("tvdb_season", sa.Integer, nullable=True),
    )

    # Copy data from the old table to the new table
    op.execute("""
        INSERT INTO animap_new (
            anidb_id, anilist_id, imdb_id, mal_id, tmdb_movie_id, tmdb_show_id,
            tvdb_id, tvdb_epoffset, tvdb_season
        )
        SELECT
            anidb_id, anilist_id, imdb_id, mal_id, tmdb_movie_id, tmdb_show_id,
            tvdb_id, tvdb_epoffset, tvdb_season
        FROM animap
    """)

    # Drop the old table and rename the new table
    op.drop_table("animap")
    op.rename_table("animap_new", "animap")

    # Recreate indexes for the new table
    op.create_index("ix_animap_anidb_id", "animap", ["anidb_id"], unique=True)
    op.create_index("ix_animap_imdb_id", "animap", ["imdb_id"], unique=False)
    op.create_index("ix_animap_mal_id", "animap", ["mal_id"], unique=False)
    op.create_index(
        "ix_animap_tmdb_movie_id", "animap", ["tmdb_movie_id"], unique=False
    )
    op.create_index("ix_animap_tmdb_show_id", "animap", ["tmdb_show_id"], unique=False)
    op.create_index("ix_animap_tvdb_id", "animap", ["tvdb_id"], unique=False)


def downgrade() -> None:
    # Reverse the migration: recreate the original table structure

    # Drop indexes explicitly
    with op.batch_alter_table("animap", schema=None) as batch_op:
        batch_op.drop_index("ix_animap_anidb_id")
        batch_op.drop_index("ix_animap_imdb_id")
        batch_op.drop_index("ix_animap_mal_id")
        batch_op.drop_index("ix_animap_tmdb_movie_id")
        batch_op.drop_index("ix_animap_tmdb_show_id")
        batch_op.drop_index("ix_animap_tvdb_id")

    # Create the old table structure
    op.create_table(
        "animap_old",
        sa.Column(
            "anilist_id", sa.Integer, primary_key=True, nullable=False
        ),  # Revert to original primary key
        sa.Column("anidb_id", sa.Integer, nullable=True),
        sa.Column("imdb_id", JSON(none_as_null=True), nullable=True),
        sa.Column("mal_id", JSON(none_as_null=True), nullable=True),
        sa.Column("tmdb_movie_id", JSON(none_as_null=True), nullable=True),
        sa.Column("tmdb_show_id", JSON(none_as_null=True), nullable=True),
        sa.Column("tvdb_id", sa.Integer, nullable=True),
        sa.Column("tvdb_epoffset", sa.Integer, nullable=True),
        sa.Column("tvdb_season", sa.Integer, nullable=True),
    )

    # Copy data back to the old table
    op.execute("""
        INSERT INTO animap_old (
            anilist_id, anidb_id, imdb_id, mal_id, tmdb_movie_id, tmdb_show_id,
            tvdb_id, tvdb_epoffset, tvdb_season
        )
        SELECT
            anilist_id, anidb_id, imdb_id, mal_id, tmdb_movie_id, tmdb_show_id,
            tvdb_id, tvdb_epoffset, tvdb_season
        FROM animap
    """)

    # Drop the current table and rename back to the original
    op.drop_table("animap")
    op.rename_table("animap_old", "animap")

    # Recreate indexes for the old table
    op.create_index("ix_animap_anilist_id", "animap", ["anilist_id"], unique=True)
    op.create_index("ix_animap_imdb_id", "animap", ["imdb_id"], unique=False)
    op.create_index("ix_animap_mal_id", "animap", ["mal_id"], unique=False)
    op.create_index(
        "ix_animap_tmdb_movie_id", "animap", ["tmdb_movie_id"], unique=False
    )
    op.create_index("ix_animap_tmdb_show_id", "animap", ["tmdb_show_id"], unique=False)
    op.create_index("ix_animap_tvdb_id", "animap", ["tvdb_id"], unique=False)
