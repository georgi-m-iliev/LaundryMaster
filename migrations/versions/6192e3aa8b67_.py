"""empty message

Revision ID: 6192e3aa8b67
Revises: 501acdb5f0c7
Create Date: 2024-01-18 18:28:56.066830

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6192e3aa8b67'
down_revision = '501acdb5f0c7'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cycle_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'washing_cycles', ['cycle_id'], ['id'])

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('cycle_id')

    # ### end Alembic commands ###