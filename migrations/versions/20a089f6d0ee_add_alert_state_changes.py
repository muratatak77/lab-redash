"""add alert_state_changes table

Revision ID: 20a089f6d0ee
Revises: 2f2a8a6f9c21
Create Date: 2026-11-07 10:12:41.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20a089f6d0ee"
down_revision = "2f2a8a6f9c21"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alert_state_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("previous_state", sa.String(length=255), nullable=False),
        sa.Column("new_state", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("notified", sa.Boolean(), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "alert_state_changes_alert_id_created_at",
        "alert_state_changes",
        ["alert_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("alert_state_changes_alert_id_created_at", table_name="alert_state_changes")
    op.drop_table("alert_state_changes")
