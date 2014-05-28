"""empty message

Revision ID: c2186e9dbdd
Revises: 4cbdf7a28c0c
Create Date: 2014-05-28 17:25:14.168653

"""

# revision identifiers, used by Alembic.
revision = 'c2186e9dbdd'
down_revision = '4cbdf7a28c0c'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('facebook_pages_users', 'created_time')
    op.drop_column('locations', 'index')
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('locations', sa.Column('index', sa.INTEGER(), server_default="nextval('locations_index_seq'::regclass)", nullable=False))
    op.add_column('facebook_pages_users', sa.Column('created_time', sa.DATE(), nullable=True))
    ### end Alembic commands ###