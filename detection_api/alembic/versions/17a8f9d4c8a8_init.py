"""init

Revision ID: 17a8f9d4c8a8
Revises: 
Create Date: 2024-11-19 17:21:13.171130

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '17a8f9d4c8a8'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def generate_uuid():
    """Helper function to generate a new UUID."""
    return str(uuid.uuid4())


def upgrade() -> None:
    # Add 'id' column as nullable first
    op.add_column('analysis_results', sa.Column('id', sa.String(), nullable=True))
    op.add_column('analysis_results',
                  sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column('analysis_results', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))

    # Populate 'id' column for existing rows
    connection = op.get_bind()
    results = connection.execute(sa.text("SELECT user_id FROM analysis_results")).fetchall()

    for row in results:
        connection.execute(
            sa.text("UPDATE analysis_results SET id = :id WHERE user_id = :user_id"),
            {"id": generate_uuid(), "user_id": row.user_id},
        )

    # Alter 'id' column to make it non-nullable
    with op.batch_alter_table('analysis_results') as batch_op:
        batch_op.alter_column('id', nullable=False)

    # drop old primary key
    with op.batch_alter_table('analysis_results') as batch_op:
        batch_op.drop_constraint('analysis_results_pkey', type_='primary')

    # Create primary key on 'id'
    with op.batch_alter_table('analysis_results') as batch_op:
        batch_op.create_primary_key('pk_analysis_results', ['id'])


def downgrade() -> None:
    # Drop primary key constraint
    with op.batch_alter_table('analysis_results') as batch_op:
        batch_op.drop_constraint('pk_analysis_results', type_='primary')

    # Remove newly added columns
    op.drop_column('analysis_results', 'id')
    op.drop_column('analysis_results', 'created_at')
    op.drop_column('analysis_results', 'is_deleted')
