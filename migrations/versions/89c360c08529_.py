"""empty message

Revision ID: 89c360c08529
Revises: 9207493a47b0
Create Date: 2023-12-31 16:10:45.805870

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '89c360c08529'
down_revision = '9207493a47b0'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('split_cycles',
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('cycle_id', sa.Integer(), nullable=True),
    sa.Column('paid', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['cycle_id'], ['washing_cycles.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('split_cycles')
    # ### end Alembic commands ###