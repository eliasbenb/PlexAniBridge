"""Migration to the PlexAniBridge mapping database

Revision ID: b2ad27e14048
Revises: 6e710e6677c0
Create Date: 2025-01-15 15:52:56.167462

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2ad27e14048"
down_revision = "6e710e6677c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("animap_new", if_exists=True)
    op.create_table(
        "animap_new",
        sa.Column("anilist_id", sa.Integer, primary_key=True),
        sa.Column("anidb_id", sa.Integer, primary_key=False, nullable=True),
        sa.Column("imdb_id", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("mal_id", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("tmdb_movie_id", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("tmdb_show_id", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("tvdb_id", sa.Integer, nullable=True),
        sa.Column("tvdb_epoffset", sa.Integer, nullable=True),
        sa.Column("tvdb_season", sa.Integer, nullable=True),
    )

    op.drop_table("animap")
    op.rename_table("animap_new", "animap")

    op.create_index("ix_animap_anidb_id", "animap", ["anidb_id"], unique=True)
    op.create_index("ix_animap_imdb_id", "animap", ["imdb_id"], unique=False)
    op.create_index("ix_animap_mal_id", "animap", ["mal_id"], unique=False)
    op.create_index(
        "ix_animap_tmdb_movie_id", "animap", ["tmdb_movie_id"], unique=False
    )
    op.create_index("ix_animap_tmdb_show_id", "animap", ["tmdb_show_id"], unique=False)
    op.create_index("ix_animap_tvdb_id", "animap", ["tvdb_id"], unique=False)

    # Clear the data in the house_keeping table
    op.execute("DELETE FROM house_keeping")


def downgrade() -> None:
    # Reverse the migration: recreate the original table structure

    # Create the old table structure
    op.create_table(
        "animap_old",
        sa.Column(
            "anilist_id", sa.Integer, primary_key=True, nullable=False
        ),  # Revert to original primary key
        sa.Column("anidb_id", sa.Integer, nullable=True),
        sa.Column("imdb_id", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("mal_id", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("tmdb_movie_id", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("tmdb_show_id", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("tvdb_id", sa.Integer, nullable=True),
        sa.Column("tvdb_epoffset", sa.Integer, nullable=True),
        sa.Column("tvdb_season", sa.Integer, nullable=True),
    )

    # Drop the current table and rename back to the original
    op.drop_table("animap")
    op.rename_table("animap_old", "animap")

    # Recreate indexes for the old table
    op.create_index("ix_animap_anilist_id", "animap", ["anilist_id"], unique=True)
    op.create_index("ix_animap_anidb_id", "animap", ["anidb_id"], unique=True)
    op.create_index("ix_animap_imdb_id", "animap", ["imdb_id"], unique=False)
    op.create_index("ix_animap_mal_id", "animap", ["mal_id"], unique=False)
    op.create_index(
        "ix_animap_tmdb_movie_id", "animap", ["tmdb_movie_id"], unique=False
    )
    op.create_index("ix_animap_tmdb_show_id", "animap", ["tmdb_show_id"], unique=False)
    op.create_index("ix_animap_tvdb_id", "animap", ["tvdb_id"], unique=False)
