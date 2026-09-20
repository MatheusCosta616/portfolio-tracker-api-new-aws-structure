from django.db import migrations


STRING_COLUMNS = [
    'USERNAME', 'CPF', 'FIRST_NAME', 'LAST_NAME', 'PASSWORD',
]


def allow_null_on_string_columns(apps, schema_editor):
    """Oracle converts '' (empty string) to NULL for VARCHAR2 columns.

    Django stores many fields as '' by default (first_name, last_name, etc.),
    which causes ORA-01400 when those columns have NOT NULL constraints.
    This migration makes them nullable so Django INSERTs succeed.
    """
    with schema_editor.connection.cursor() as cursor:
        for col in STRING_COLUMNS:
            cursor.execute(
                f"SELECT COUNT(*) FROM user_tab_columns "
                f"WHERE table_name = 'USERS' AND column_name = '{col}' AND nullable = 'N'"
            )
            if cursor.fetchone()[0] > 0:
                cursor.execute(f"ALTER TABLE USERS MODIFY ({col} NULL)")


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_fix_oracle_not_null_defaults'),
    ]

    operations = [
        migrations.RunPython(allow_null_on_string_columns, migrations.RunPython.noop),
    ]
