import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='StripeEvent',
            fields=[
                ('event_id', models.CharField(max_length=255, primary_key=True, serialize=False)),
                ('type', models.CharField(max_length=100)),
                ('payload', models.JSONField()),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-received_at'],
            },
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('plan', models.CharField(choices=[('free', 'Free'), ('starter', 'Starter'), ('pro', 'Pro')], default='free', max_length=10)),
                ('status', models.CharField(choices=[('active', 'Active'), ('trialing', 'Trialing'), ('past_due', 'Past due'), ('canceled', 'Canceled'), ('incomplete', 'Incomplete')], default='active', max_length=12)),
                ('provider', models.CharField(choices=[('demo', 'Demo'), ('stripe', 'Stripe')], default='demo', max_length=6)),
                ('stripe_customer_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('stripe_subscription_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('current_period_start', models.DateTimeField(blank=True, null=True)),
                ('current_period_end', models.DateTimeField(blank=True, null=True)),
                ('cancel_at_period_end', models.BooleanField(default=False)),
                ('organization', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subscription', to='accounts.organization')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='UsageCounter',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('period_start', models.DateField(help_text='First day of the month.')),
                ('messages', models.PositiveIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='usage_counters', to='accounts.organization')),
            ],
            options={
                'ordering': ['-period_start'],
                'constraints': [models.UniqueConstraint(fields=('organization', 'period_start'), name='billing_usage_unique_period')],
            },
        ),
    ]
