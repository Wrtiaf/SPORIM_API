"""combos moderation and event resolution

Revision ID: 443c6ef7ff13
Revises: e181c0c7cb3f
Create Date: 2026-11-06 22:20:12.931563

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '443c6ef7ff13'
down_revision: Union[str, None] = 'e181c0c7cb3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('moderation_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('moderator_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.Enum('APPROVE', 'REJECT', 'RESOLVE', 'CANCEL', name='moderation_action', native_enum=False, length=20), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], name=op.f('fk_moderation_log_event_id_events'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['moderator_id'], ['users.id'], name=op.f('fk_moderation_log_moderator_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_moderation_log'))
    )
    op.create_index(op.f('ix_moderation_log_event_id'), 'moderation_log', ['event_id'], unique=False)
    op.create_index(op.f('ix_moderation_log_moderator_id'), 'moderation_log', ['moderator_id'], unique=False)

    op.drop_table('combo_bets')
    op.execute("DELETE FROM combos")

    with op.batch_alter_table('combos') as batch_op:
        batch_op.add_column(sa.Column('side', sa.Enum('YES', 'NO', name='combo_side', native_enum=False, length=10), nullable=False))
        batch_op.add_column(sa.Column('amount', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('entry_coefficient', sa.Float(), nullable=False))
        batch_op.add_column(sa.Column('potential_payout', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('payout', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('settled_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.drop_column('total_coefficient')

    op.create_table('combo_legs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('combo_id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('option_id', sa.Integer(), nullable=False),
    sa.Column('choice', sa.Enum('YES', 'NO', name='combo_leg_choice', native_enum=False, length=10), nullable=False),
    sa.Column('coefficient', sa.Float(), nullable=False),
    sa.Column('result', sa.Enum('PENDING', 'WON', 'LOST', 'HALF', name='combo_leg_result', native_enum=False, length=20), server_default='PENDING', nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['combo_id'], ['combos.id'], name=op.f('fk_combo_legs_combo_id_combos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], name=op.f('fk_combo_legs_event_id_events'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['option_id'], ['options.id'], name=op.f('fk_combo_legs_option_id_options'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_combo_legs')),
    sa.UniqueConstraint('combo_id', 'event_id', name='uq_combo_legs_combo_id_event_id')
    )
    op.create_index(op.f('ix_combo_legs_combo_id'), 'combo_legs', ['combo_id'], unique=False)
    op.create_index(op.f('ix_combo_legs_event_id'), 'combo_legs', ['event_id'], unique=False)
    op.create_index(op.f('ix_combo_legs_option_id'), 'combo_legs', ['option_id'], unique=False)
    op.create_index(op.f('ix_combo_legs_result'), 'combo_legs', ['result'], unique=False)

    with op.batch_alter_table('complaints') as batch_op:
        batch_op.add_column(sa.Column('resolved_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('resolution_comment', sa.Text(), nullable=True))
        batch_op.create_foreign_key(op.f('fk_complaints_resolved_by_users'), 'users', ['resolved_by'], ['id'], ondelete='SET NULL')
    op.create_index(
        'uq_complaints_pending_reporter_event',
        'complaints',
        ['reporter_id', 'event_id'],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
        sqlite_where=sa.text("status = 'PENDING'"),
    )

    with op.batch_alter_table('events') as batch_op:
        batch_op.add_column(sa.Column('winning_option_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rejection_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('approved_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key('fk_events_winning_option_id_options', 'options', ['winning_option_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(op.f('fk_events_approved_by_users'), 'users', ['approved_by'], ['id'], ondelete='SET NULL')
        batch_op.create_check_constraint('ck_events_fixed_coefficient_gt_one', 'fixed_coefficient > 1')
    op.create_index(op.f('ix_events_deleted_at'), 'events', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_events_winning_option_id'), 'events', ['winning_option_id'], unique=False)

    with op.batch_alter_table('options') as batch_op:
        batch_op.create_check_constraint('ck_options_yes_count_non_negative', 'yes_count >= 0')
        batch_op.create_check_constraint('ck_options_no_count_non_negative', 'no_count >= 0')
        batch_op.create_check_constraint('ck_options_current_percentage_range', 'current_percentage >= 0 AND current_percentage <= 100')

    with op.batch_alter_table('bets') as batch_op:
        batch_op.create_check_constraint('ck_bets_amount_positive', 'amount > 0')

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('total_bets')
        batch_op.drop_column('won_bets')
    op.create_index('uq_users_username_lower', 'users', [sa.text('lower(username)')], unique=True)


def downgrade() -> None:
    op.drop_index('uq_users_username_lower', table_name='users')
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('won_bets', sa.Integer(), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('total_bets', sa.Integer(), server_default=sa.text('0'), nullable=False))

    with op.batch_alter_table('bets') as batch_op:
        batch_op.drop_constraint('ck_bets_amount_positive', type_='check')

    with op.batch_alter_table('options') as batch_op:
        batch_op.drop_constraint('ck_options_current_percentage_range', type_='check')
        batch_op.drop_constraint('ck_options_no_count_non_negative', type_='check')
        batch_op.drop_constraint('ck_options_yes_count_non_negative', type_='check')

    op.drop_index(op.f('ix_events_winning_option_id'), table_name='events')
    op.drop_index(op.f('ix_events_deleted_at'), table_name='events')
    with op.batch_alter_table('events') as batch_op:
        batch_op.drop_constraint(op.f('fk_events_approved_by_users'), type_='foreignkey')
        batch_op.drop_constraint('fk_events_winning_option_id_options', type_='foreignkey')
        batch_op.drop_constraint('ck_events_fixed_coefficient_gt_one', type_='check')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approved_by')
        batch_op.drop_column('rejection_reason')
        batch_op.drop_column('winning_option_id')

    op.drop_index('uq_complaints_pending_reporter_event', table_name='complaints')
    with op.batch_alter_table('complaints') as batch_op:
        batch_op.drop_constraint(op.f('fk_complaints_resolved_by_users'), type_='foreignkey')
        batch_op.drop_column('resolution_comment')
        batch_op.drop_column('resolved_by')

    op.drop_index(op.f('ix_combo_legs_result'), table_name='combo_legs')
    op.drop_index(op.f('ix_combo_legs_option_id'), table_name='combo_legs')
    op.drop_index(op.f('ix_combo_legs_event_id'), table_name='combo_legs')
    op.drop_index(op.f('ix_combo_legs_combo_id'), table_name='combo_legs')
    op.drop_table('combo_legs')

    with op.batch_alter_table('combos') as batch_op:
        batch_op.add_column(sa.Column('total_coefficient', sa.Float(), server_default=sa.text('(1.0)'), nullable=False))
        batch_op.drop_column('settled_at')
        batch_op.drop_column('payout')
        batch_op.drop_column('potential_payout')
        batch_op.drop_column('entry_coefficient')
        batch_op.drop_column('amount')
        batch_op.drop_column('side')

    op.create_table('combo_bets',
    sa.Column('combo_id', sa.Integer(), nullable=False),
    sa.Column('bet_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['bet_id'], ['bets.id'], name=op.f('fk_combo_bets_bet_id_bets'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['combo_id'], ['combos.id'], name=op.f('fk_combo_bets_combo_id_combos'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('combo_id', 'bet_id', name=op.f('pk_combo_bets')),
    sa.UniqueConstraint('bet_id', name=op.f('uq_combo_bets_bet_id'))
    )

    op.drop_index(op.f('ix_moderation_log_moderator_id'), table_name='moderation_log')
    op.drop_index(op.f('ix_moderation_log_event_id'), table_name='moderation_log')
    op.drop_table('moderation_log')
