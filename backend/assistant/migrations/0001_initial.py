import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
        ('knowledge', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Conversation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('channel', models.CharField(choices=[('widget', 'Website widget'), ('playground', 'Dashboard playground')], max_length=12)),
                ('status', models.CharField(choices=[('open', 'Open'), ('handed_off', 'Handed off'), ('closed', 'Closed')], default='open', max_length=12)),
                ('title', models.CharField(blank=True, help_text='First question, shortened.', max_length=200)),
                ('visitor_id', models.CharField(blank=True, max_length=64)),
                ('origin', models.CharField(blank=True, max_length=255)),
                ('page_url', models.URLField(blank=True, max_length=1000)),
                ('ip_hash', models.CharField(blank=True, max_length=64)),
                ('user_agent', models.CharField(blank=True, max_length=300)),
                ('message_count', models.PositiveIntegerField(default=0)),
                ('last_message_at', models.DateTimeField(blank=True, null=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conversations', to='accounts.organization')),
                ('started_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-last_message_at', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='HandoffTicket',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('open', 'Open'), ('pending', 'Pending'), ('resolved', 'Resolved')], default='open', max_length=10)),
                ('requester_email', models.EmailField(max_length=254)),
                ('requester_name', models.CharField(blank=True, max_length=150)),
                ('note', models.TextField(blank=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tickets', to='assistant.conversation')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tickets', to='accounts.organization')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant')], max_length=10)),
                ('content', models.TextField(blank=True)),
                ('normalized_content', models.CharField(blank=True, max_length=300)),
                ('status', models.CharField(choices=[('streaming', 'Streaming'), ('complete', 'Complete'), ('truncated', 'Truncated'), ('failed', 'Failed')], default='complete', max_length=10)),
                ('answer_type', models.CharField(blank=True, choices=[('answered', 'Answered'), ('not_found', 'Not found in documentation'), ('refused', 'Refused'), ('error', 'Error')], max_length=10)),
                ('provider', models.CharField(blank=True, choices=[('ollama', 'Ollama'), ('claude', 'Claude API'), ('extractive', 'Extractive (offline)')], max_length=12)),
                ('model', models.CharField(blank=True, help_text='Model that actually served the answer.', max_length=100)),
                ('latency_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('first_token_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('input_tokens', models.PositiveIntegerField(default=0)),
                ('output_tokens', models.PositiveIntegerField(default=0)),
                ('cache_read_input_tokens', models.PositiveIntegerField(default=0)),
                ('cache_creation_input_tokens', models.PositiveIntegerField(default=0)),
                ('cost_usd', models.DecimalField(decimal_places=6, default=0, max_digits=12)),
                ('top_score', models.FloatField(blank=True, null=True)),
                ('rating', models.SmallIntegerField(blank=True, choices=[(-1, 'Thumbs down'), (1, 'Thumbs up')], null=True)),
                ('feedback_comment', models.TextField(blank=True)),
                ('rated_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='assistant.conversation')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='accounts.organization')),
                ('reply_to', models.ForeignKey(blank=True, help_text='For assistant messages: the user message being answered.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='replies', to='assistant.message')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='Citation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('marker', models.PositiveSmallIntegerField(help_text='The n in [n].')),
                ('document_title', models.CharField(max_length=255)),
                ('location', models.CharField(blank=True, max_length=120)),
                ('snippet', models.TextField()),
                ('score', models.FloatField(blank=True, null=True)),
                ('chunk', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='knowledge.chunk')),
                ('document', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='knowledge.document')),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='citations', to='assistant.message')),
            ],
            options={
                'ordering': ['marker'],
            },
        ),
        migrations.AddIndex(
            model_name='conversation',
            index=models.Index(fields=['organization', '-last_message_at'], name='assistant_conv_org_recent'),
        ),
        migrations.AddIndex(
            model_name='conversation',
            index=models.Index(fields=['organization', 'channel'], name='assistant_conv_org_channel'),
        ),
        migrations.AddIndex(
            model_name='conversation',
            index=models.Index(fields=['organization', 'visitor_id'], name='assistant_conv_org_visitor'),
        ),
        migrations.AddIndex(
            model_name='handoffticket',
            index=models.Index(fields=['organization', 'status'], name='assistant_ticket_org_status'),
        ),
        migrations.AddIndex(
            model_name='message',
            index=models.Index(fields=['conversation', 'created_at'], name='assistant_msg_conv_created'),
        ),
        migrations.AddIndex(
            model_name='message',
            index=models.Index(fields=['organization', 'created_at'], name='assistant_msg_org_created'),
        ),
        migrations.AddIndex(
            model_name='message',
            index=models.Index(fields=['organization', 'answer_type'], name='assistant_msg_org_answer'),
        ),
        migrations.AddIndex(
            model_name='message',
            index=models.Index(fields=['organization', 'normalized_content'], name='assistant_msg_org_question'),
        ),
        migrations.AddConstraint(
            model_name='citation',
            constraint=models.UniqueConstraint(fields=('message', 'marker'), name='assistant_citation_unique_marker'),
        ),
    ]
