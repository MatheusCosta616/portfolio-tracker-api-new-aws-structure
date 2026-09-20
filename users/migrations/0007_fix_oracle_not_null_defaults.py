from django.db import migrations


DJANGO_KNOWN_COLUMNS = {
    'ID', 'PASSWORD', 'LAST_LOGIN', 'IS_SUPERUSER', 'FIRST_NAME', 'LAST_NAME',
    'IS_STAFF', 'IS_ACTIVE', 'DATE_JOINED', 'EMAIL', 'USERNAME', 'CPF',
}


def fix_not_null_defaults(apps, schema_editor):
    """For every NOT-NULL column in USERS that has no DEFAULT and is unknown to
    Django, set an appropriate default so Django INSERTs don't fail with ORA-01400.

    This covers legacy columns added by the FIAP schema (NAME, CREATED_AT, etc.)
    that pre-date the Django project.
    """
    with schema_editor.connection.cursor() as cursor:
        # Find columns that are NOT NULL, have no data_default, and are not
        # handled by Django's model
        cursor.execute("""
            SELECT column_name, data_type
            FROM user_tab_columns
            WHERE table_name = 'USERS'
              AND nullable = 'N'
              AND data_default IS NULL
        """)
        rows = cursor.fetchall()

        for col_name, data_type in rows:
            if col_name in DJANGO_KNOWN_COLUMNS:
                continue

            if data_type in ('NUMBER', 'INTEGER', 'FLOAT', 'BINARY_FLOAT', 'BINARY_DOUBLE'):
                default = '0'
            elif data_type.startswith('TIMESTAMP') or data_type == 'DATE':
                default = 'CURRENT_TIMESTAMP'
            else:
                default = "' '"

            # Oracle allows MODIFY without repeating the data type — only changes the default
            cursor.execute(
                f"ALTER TABLE USERS MODIFY ({col_name} DEFAULT {default})"
            )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_fix_oracle_created_at_default'),
    ]

    operations = [
        migrations.RunPython(fix_not_null_defaults, migrations.RunPython.noop),
    ]
