from django.db import migrations


def fix_created_at_default(apps, schema_editor):
    """Add a DEFAULT CURRENT_TIMESTAMP to the pre-existing CREATED_AT column
    in the Oracle USERS table so Django INSERT statements do not fail with
    ORA-01400 when the column is not included in the INSERT field list."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM user_tab_columns "
            "WHERE table_name = 'USERS' AND column_name = 'CREATED_AT'"
        )
        if cursor.fetchone()[0] > 0:
            cursor.execute(
                "ALTER TABLE USERS MODIFY (CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_ensure_auth_columns'),
    ]

    operations = [
        migrations.RunPython(fix_created_at_default, migrations.RunPython.noop),
    ]
