"""empty message

Revision ID: bbed60bf1361
Revises: b416b11515f5
Create Date: 2024-01-15 22:43:03.031367

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bbed60bf1361'
down_revision = 'b416b11515f5'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('washing_machine', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cycle_remaining_minutes', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('candy_device_id', sa.String(length=512), nullable=False))
        batch_op.add_column(sa.Column('candy_appliance_id', sa.String(length=512), nullable=False))
        batch_op.add_column(sa.Column('candy_api_token', sa.String(length=5000), nullable=True))
        batch_op.add_column(sa.Column('candy_api_refresh_token', sa.String(length=512), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('washing_machine', schema=None) as batch_op:
        batch_op.drop_column('cycle_remaining_minutes')
        batch_op.drop_column('candy_api_refresh_token')
        batch_op.drop_column('candy_api_token')
        batch_op.drop_column('candy_appliance_id')
        batch_op.drop_column('candy_device_id')

    # ### end Alembic commands ###