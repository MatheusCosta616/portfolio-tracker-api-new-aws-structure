from django.db import migrations


def _has_column(cursor, table, column):
    cursor.execute(
        "SELECT COUNT(*) FROM user_tab_columns "
        f"WHERE table_name = '{table.upper()}' AND column_name = '{column.upper()}'"
    )
    return cursor.fetchone()[0] > 0


def _add_if_missing(cursor, table, column, ddl):
    if not _has_column(cursor, table, column):
        cursor.execute(ddl)


def ensure_abstractuser_columns(apps, schema_editor):
    """Add remaining AbstractUser columns that may be absent from a legacy Oracle table."""
    with schema_editor.connection.cursor() as cursor:
        t = 'USERS'
        _add_if_missing(cursor, t, 'FIRST_NAME',
            "ALTER TABLE USERS ADD (FIRST_NAME VARCHAR2(150 CHAR) DEFAULT ' ' NOT NULL)")
        _add_if_missing(cursor, t, 'LAST_NAME',
            "ALTER TABLE USERS ADD (LAST_NAME VARCHAR2(150 CHAR) DEFAULT ' ' NOT NULL)")
        _add_if_missing(cursor, t, 'IS_STAFF',
            "ALTER TABLE USERS ADD (IS_STAFF NUMBER(1,0) DEFAULT 0 NOT NULL)")
        _add_if_missing(cursor, t, 'IS_ACTIVE',
            "ALTER TABLE USERS ADD (IS_ACTIVE NUMBER(1,0) DEFAULT 1 NOT NULL)")
        _add_if_missing(cursor, t, 'IS_SUPERUSER',
            "ALTER TABLE USERS ADD (IS_SUPERUSER NUMBER(1,0) DEFAULT 0 NOT NULL)")
        _add_if_missing(cursor, t, 'DATE_JOINED',
            "ALTER TABLE USERS ADD (DATE_JOINED TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)")
        _add_if_missing(cursor, t, 'LAST_LOGIN',
            "ALTER TABLE USERS ADD (LAST_LOGIN TIMESTAMP NULL)")


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_ensure_username_column'),
    ]

    operations = [
        migrations.RunPython(ensure_abstractuser_columns, migrations.RunPython.noop),
    ]
