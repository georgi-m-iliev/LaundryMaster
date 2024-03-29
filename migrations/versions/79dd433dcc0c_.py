"""empty message

Revision ID: 79dd433dcc0c
Revises: 89c360c08529
Create Date: 2024-01-10 23:41:52.948215

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '79dd433dcc0c'
down_revision = '89c360c08529'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notification_task_id', sa.String(length=512), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.drop_column('notification_task_id')

    # ### end Alembic commands ###
