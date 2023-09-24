"""empty message

Revision ID: 5fb77350ee50
Revises: dc8f3318685c
Create Date: 2023-09-24 21:54:54.064512

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5fb77350ee50'
down_revision = 'dc8f3318685c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('washing_machine',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kwh', sa.Numeric(precision=20, scale=4), nullable=True),
    sa.Column('cost_kwh', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('washing_cycles', schema=None) as batch_op:
        batch_op.alter_column('startkwh',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=20, scale=4),
               existing_nullable=True)
        batch_op.alter_column('endkwh',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=20, scale=4),
               existing_nullable=True)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('washing_cycles', schema=None) as batch_op:
        batch_op.alter_column('endkwh',
               existing_type=sa.Numeric(precision=20, scale=4),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=True)
        batch_op.alter_column('startkwh',
               existing_type=sa.Numeric(precision=20, scale=4),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=True)

    op.drop_table('washing_machine')
    # ### end Alembic commands ###
