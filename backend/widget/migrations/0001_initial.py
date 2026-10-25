import django.contrib.postgres.fields
import django.core.validators
import django.db.models.deletion
import uuid
import widget.models
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='WidgetConfig',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('site_key', models.CharField(default=widget.models.generate_site_key, max_length=64, unique=True)),
                ('is_enabled', models.BooleanField(default=True)),
                ('allowed_origins', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=255), blank=True, default=list, help_text='Exact origins such as "https://shop.example.com".', size=None)),
                ('title', models.CharField(default='Help', max_length=60)),
                ('greeting', models.CharField(default='Hi! Ask me anything about our products and policies.', max_length=300)),
                ('brand_color', models.CharField(default='#4f46e5', max_length=7, validators=[django.core.validators.RegexValidator('^#[0-9a-fA-F]{6}$', 'Use a hex colour like #4f46e5.')])),
                ('position', models.CharField(choices=[('right', 'Bottom right'), ('left', 'Bottom left')], default='right', max_length=5)),
                ('organization', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='widget', to='accounts.organization')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
