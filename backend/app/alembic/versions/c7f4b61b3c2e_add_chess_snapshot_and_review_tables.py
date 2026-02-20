"""Add chess snapshot and review tables

Revision ID: c7f4b61b3c2e
Revises: fe56fa70289e
Create Date: 2026-02-16 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c7f4b61b3c2e"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chesspositionsnapshot",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("move_count", sa.Integer(), nullable=False),
        sa.Column("fen", sa.String(length=120), nullable=False),
        sa.Column("moves_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "move_count", name="uq_chess_snapshot_game_move_count"),
    )
    op.create_index(
        op.f("ix_chesspositionsnapshot_game_id"),
        "chesspositionsnapshot",
        ["game_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chesspositionsnapshot_move_count"),
        "chesspositionsnapshot",
        ["move_count"],
        unique=False,
    )

    op.create_table(
        "chessgamereview",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("review_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", name="uq_chess_game_review_game_id"),
    )
    op.create_index(
        op.f("ix_chessgamereview_game_id"),
        "chessgamereview",
        ["game_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_chessgamereview_game_id"), table_name="chessgamereview")
    op.drop_table("chessgamereview")

    op.drop_index(op.f("ix_chesspositionsnapshot_move_count"), table_name="chesspositionsnapshot")
    op.drop_index(op.f("ix_chesspositionsnapshot_game_id"), table_name="chesspositionsnapshot")
    op.drop_table("chesspositionsnapshot")

