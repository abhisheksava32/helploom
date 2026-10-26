import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('knowledge', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='IngestionJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('trigger', models.CharField(choices=[('upload', 'Upload'), ('reindex', 'Re-index'), ('reembed', 'Re-embed')], default='upload', max_length=10)),
                ('status', models.CharField(choices=[('running', 'Running'), ('succeeded', 'Succeeded'), ('failed', 'Failed')], default='running', max_length=10)),
                ('embedder', models.CharField(blank=True, max_length=100)),
                ('chunk_count', models.PositiveIntegerField(default=0)),
                ('extract_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('embed_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('duration_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True, help_text='Friendly reason shown to the user.')),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ingestion_jobs', to='knowledge.document')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='accounts.organization')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['document', '-created_at'], name='knowledge_job_doc_recent')],
            },
        ),
    ]
