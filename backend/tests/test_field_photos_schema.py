from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_SQL = (BACKEND_DIR / "migrations" / "field_photos_storage.sql").read_text()
SCHEMA_SQL = (BACKEND_DIR / "schema.sql").read_text()


def test_fields_table_already_has_nullable_image_url_column() -> None:
    assert "image_url text" in SCHEMA_SQL


def test_field_photos_storage_bucket_is_private_and_limited() -> None:
    assert "storage.buckets" in MIGRATION_SQL
    assert "'field-photos'" in MIGRATION_SQL
    assert "false" in MIGRATION_SQL
    assert "5242880" in MIGRATION_SQL
    assert "image/jpeg" in MIGRATION_SQL
    assert "image/png" in MIGRATION_SQL
    assert "image/webp" in MIGRATION_SQL
    assert "public = excluded.public" in MIGRATION_SQL
