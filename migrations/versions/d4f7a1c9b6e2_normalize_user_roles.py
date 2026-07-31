"""normalize user roles into roles/user_roles tables

Revision ID: d4f7a1c9b6e2
Revises: ac3f8e358ae9
Create Date: 2026-07-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f7a1c9b6e2'
down_revision: Union[str, Sequence[str], None] = 'ac3f8e358ae9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('user_roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'role_id', name='uq_user_roles_user_id_role_id')
    )
    op.create_index(op.f('ix_user_roles_role_id'), 'user_roles', ['role_id'], unique=False)
    op.create_index(op.f('ix_user_roles_user_id'), 'user_roles', ['user_id'], unique=False)

    # Backfill: turn each existing users.roles array entry into a role + user_roles row.
    connection = op.get_bind()
    connection.execute(sa.text(
        """
        INSERT INTO roles (name)
        SELECT DISTINCT unnest(roles) FROM users
        ON CONFLICT (name) DO NOTHING
        """
    ))
    connection.execute(sa.text(
        """
        INSERT INTO user_roles (user_id, role_id)
        SELECT u.id, r.id
        FROM users u
        CROSS JOIN LATERAL unnest(u.roles) AS role_name
        JOIN roles r ON r.name = role_name
        ON CONFLICT (user_id, role_id) DO NOTHING
        """
    ))

    op.drop_column('users', 'roles')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('roles', sa.ARRAY(sa.String()), nullable=False, server_default='{}'))

    connection = op.get_bind()
    connection.execute(sa.text(
        """
        UPDATE users u
        SET roles = COALESCE(sub.role_names, '{}')
        FROM (
            SELECT ur.user_id, array_agg(r.name ORDER BY ur.created_at) AS role_names
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            GROUP BY ur.user_id
        ) sub
        WHERE u.id = sub.user_id
        """
    ))

    op.drop_index(op.f('ix_user_roles_user_id'), table_name='user_roles')
    op.drop_index(op.f('ix_user_roles_role_id'), table_name='user_roles')
    op.drop_table('user_roles')
    op.drop_table('roles')
