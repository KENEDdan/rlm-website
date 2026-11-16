"""Database-level enforcement: the audit table rejects UPDATE and DELETE (and TRUNCATE)."""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION audit_log_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditlog is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit_auditlog;
CREATE TRIGGER audit_log_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();

DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_auditlog;
CREATE TRIGGER audit_log_no_truncate
    BEFORE TRUNCATE ON audit_auditlog
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit_auditlog;
DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_auditlog;
DROP FUNCTION IF EXISTS audit_log_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
