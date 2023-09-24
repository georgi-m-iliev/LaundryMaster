"""empty message

Revision ID: 48a0b6007211
Revises: 9f55005989a5
Create Date: 2023-09-24 22:39:58.138394

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '48a0b6007211'
down_revision = '9f55005989a5'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('washing_machine', schema=None) as batch_op:
        batch_op.add_column(sa.Column('costperkwh', sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.drop_column('cost_kwh')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('washing_machine', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cost_kwh', sa.NUMERIC(precision=10, scale=2), autoincrement=False, nullable=True))
        batch_op.drop_column('costperkwh')

    # ### end Alembic commands ###
