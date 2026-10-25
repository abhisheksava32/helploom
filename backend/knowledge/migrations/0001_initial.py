import django.contrib.postgres.fields
import django.contrib.postgres.indexes
import django.contrib.postgres.search
import django.db.models.deletion
import knowledge.models
import pgvector.django.indexes
import pgvector.django.vector
import uuid
from django.conf import settings
from django.db import migrations, models
from pgvector.django import VectorExtension


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Installs pgvector in a fresh database, including the pytest test database.
        VectorExtension(),
        migrations.CreateModel(
            name='Collection',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=120)),
                ('description', models.TextField(blank=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='collections', to='accounts.organization')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=255)),
                ('original_filename', models.CharField(max_length=255)),
                ('file', models.FileField(max_length=500, upload_to=knowledge.models.document_upload_path)),
                ('content_type', models.CharField(max_length=100)),
                ('file_size', models.PositiveBigIntegerField()),
                ('checksum', models.CharField(help_text='SHA-256 of the file bytes.', max_length=64)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('processing', 'Processing'), ('ready', 'Ready'), ('failed', 'Failed')], default='queued', max_length=12)),
                ('error_message', models.TextField(blank=True)),
                ('extracted_text', models.TextField(blank=True)),
                ('page_count', models.PositiveIntegerField(blank=True, null=True)),
                ('chunk_count', models.PositiveIntegerField(default=0)),
                ('token_count', models.PositiveIntegerField(default=0)),
                ('tags', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=50), blank=True, default=list, size=None)),
                ('embedder', models.CharField(blank=True, max_length=100)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('collection', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='documents', to='knowledge.collection')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='accounts.organization')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Chunk',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ordinal', models.PositiveIntegerField(help_text='Position of the chunk inside its document.')),
                ('text', models.TextField()),
                ('heading', models.CharField(blank=True, help_text='Nearest section heading.', max_length=255)),
                ('page_number', models.PositiveIntegerField(blank=True, null=True)),
                ('location', models.CharField(blank=True, help_text='Human label, e.g. "Page 3".', max_length=120)),
                ('char_start', models.PositiveIntegerField(default=0)),
                ('char_end', models.PositiveIntegerField(default=0)),
                ('token_count', models.PositiveIntegerField(default=0)),
                ('embedding', pgvector.django.vector.VectorField(blank=True, dimensions=768, null=True)),
                ('embedder', models.CharField(help_text='Name of the embedder, e.g. "hashing-v1".', max_length=100)),
                ('search_vector', models.GeneratedField(db_persist=True, expression=django.contrib.postgres.search.CombinedSearchVector(django.contrib.postgres.search.SearchVector('heading', config='english', weight='A'), '||', django.contrib.postgres.search.SearchVector('text', config='english', weight='B'), django.contrib.postgres.search.SearchConfig('english')), output_field=django.contrib.postgres.search.SearchVectorField())),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='accounts.organization')),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chunks', to='knowledge.document')),
            ],
            options={
                'ordering': ['document', 'ordinal'],
            },
        ),
        migrations.AddConstraint(
            model_name='collection',
            constraint=models.UniqueConstraint(fields=('organization', 'name'), name='knowledge_collection_unique_name'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['organization', 'status'], name='knowledge_doc_org_status'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['organization', '-created_at'], name='knowledge_doc_org_created'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=django.contrib.postgres.indexes.GinIndex(fields=['tags'], name='knowledge_doc_tags_gin'),
        ),
        migrations.AddConstraint(
            model_name='document',
            constraint=models.UniqueConstraint(fields=('organization', 'checksum'), name='knowledge_document_unique_checksum'),
        ),
        migrations.AddIndex(
            model_name='chunk',
            index=pgvector.django.indexes.HnswIndex(ef_construction=64, fields=['embedding'], m=16, name='knowledge_chunk_embedding_hnsw', opclasses=['vector_cosine_ops']),
        ),
        migrations.AddIndex(
            model_name='chunk',
            index=django.contrib.postgres.indexes.GinIndex(fields=['search_vector'], name='knowledge_chunk_search_gin'),
        ),
        migrations.AddIndex(
            model_name='chunk',
            index=models.Index(fields=['organization', 'document'], name='knowledge_chunk_org_doc'),
        ),
        migrations.AddConstraint(
            model_name='chunk',
            constraint=models.UniqueConstraint(fields=('document', 'ordinal'), name='knowledge_chunk_unique_ordinal'),
        ),
    ]
