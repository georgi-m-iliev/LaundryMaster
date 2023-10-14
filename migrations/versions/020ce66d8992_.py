"""empty message

Revision ID: 020ce66d8992
Revises: 4d0d4e5f2b3f
Create Date: 2023-10-14 21:31:24.213166

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '020ce66d8992'
down_revision = '4d0d4e5f2b3f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('push_subscription', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_unique_constraint(None, ['id'])
        batch_op.create_foreign_key(None, 'users', ['user_id'], ['id'])

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('push_subscription', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='unique')
        batch_op.drop_column('user_id')

    # ### end Alembic commands ###
