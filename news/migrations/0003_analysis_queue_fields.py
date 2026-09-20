from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0002_analysis'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysis',
            name='attempts',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='analysis',
            name='finished_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='analysis',
            name='last_error',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='analysis',
            name='model_version',
            field=models.CharField(default='rules-v2.0.0', max_length=50),
        ),
        migrations.AddField(
            model_name='analysis',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='analysis',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pendente'),
                    ('processing', 'Processando'),
                    ('completed', 'Concluída'),
                    ('failed', 'Falhou'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='analysis',
            name='ticker',
            field=models.CharField(blank=True, db_index=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='analysis',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='analysis',
            name='analise',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterModelOptions(
            name='analysis',
            options={'ordering': ['created_at', 'id']},
        ),
    ]
