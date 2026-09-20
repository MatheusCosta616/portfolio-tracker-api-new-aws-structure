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


def ensure_all_missing_columns(apps, schema_editor):
    """Add every column from the AbstractUser + custom User model that may be absent."""
    with schema_editor.connection.cursor() as cursor:
        t = 'USERS'
        # Django AbstractUser core auth columns
        _add_if_missing(cursor, t, 'PASSWORD',
            "ALTER TABLE USERS ADD (PASSWORD VARCHAR2(128 CHAR) DEFAULT ' ' NOT NULL)")
        _add_if_missing(cursor, t, 'EMAIL',
            "ALTER TABLE USERS ADD (EMAIL VARCHAR2(254 CHAR) DEFAULT ' ' NOT NULL)")
        # Repeating earlier columns in case previous migration did not run them
        _add_if_missing(cursor, t, 'USERNAME',
            "ALTER TABLE USERS ADD (USERNAME VARCHAR2(150 CHAR) DEFAULT ' ' NOT NULL)")
        _add_if_missing(cursor, t, 'CPF',
            "ALTER TABLE USERS ADD (CPF VARCHAR2(14 CHAR) DEFAULT ' ' NOT NULL)")
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
        ('users', '0004_ensure_abstractuser_columns'),
    ]

    operations = [
        migrations.RunPython(ensure_all_missing_columns, migrations.RunPython.noop),
    ]
