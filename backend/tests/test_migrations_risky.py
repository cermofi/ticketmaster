from __future__ import annotations

from ticketmaster.services import migrations


def test_drop_column_migration_is_risky():
    assert migrations.is_risky_migration_sql("ALTER TABLE tickets DROP COLUMN IF EXISTS custom_owner;")


def test_create_index_migration_is_safe():
    assert not migrations.is_risky_migration_sql("CREATE INDEX IF NOT EXISTS idx ON tickets (status);")
