"""merge reminders and referrals heads

Revision ID: b2c3merge01
Revises: 0113ac29708d, a3b1referral01
Create Date: 2026-06-19
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "b2c3merge01"
down_revision: Union[str, Sequence[str]] = ("0113ac29708d", "a3b1referral01")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
