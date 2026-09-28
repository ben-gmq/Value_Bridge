"""Soft delete, in one place (§7.12 lifecycle). Sets is_active, deleted_at and deleted_by
together, so "revoked at / by" (§5.3) is never half-recorded."""
from datetime import UTC, datetime


def soft_delete(obj, actor_id: int) -> None:
    obj.is_active = False
    obj.deleted_at = datetime.now(UTC)
    obj.deleted_by = actor_id
