from tortoise import migrations
from tortoise.migrations import operations as ops
from app.models import BookingChannel, FeedSyncStatus
from uuid import uuid4
from tortoise import fields
from tortoise.migrations.constraints import UniqueConstraint

class Migration(migrations.Migration):
    dependencies = [('models', '0002_auto_20260706_1444')]

    initial = False

    operations = [
        ops.CreateModel(
            name='ExternalCalendarFeed',
            fields=[
                ('id', fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('property_id', fields.UUIDField()),
                ('channel', fields.CharEnumField(default=BookingChannel.BOOKING_COM, description='PLATFORM: platform\nBOOKING_COM: booking_com', enum_type=BookingChannel, max_length=11)),
                ('url', fields.CharField(max_length=2048)),
                ('is_active', fields.BooleanField(default=True, db_index=True)),
                ('last_synced_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('last_status', fields.CharEnumField(null=True, description='OK: ok\nFETCH_ERROR: fetch_error\nPARSE_ERROR: parse_error', enum_type=FeedSyncStatus, max_length=11)),
                ('last_error', fields.CharField(null=True, max_length=1024)),
                ('content_hash', fields.CharField(null=True, max_length=64)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ],
            options={'table': 'external_calendar_feeds', 'app': 'models', 'pk_attr': 'id', 'table_description': 'An external iCal export URL an owner links to a property (BTR-41).'},
            bases=['AbstractModel'],
        ),
        ops.AddField(
            model_name='Booking',
            name='channel',
            field=fields.CharEnumField(default=BookingChannel.PLATFORM, description='PLATFORM: platform\nBOOKING_COM: booking_com', enum_type=BookingChannel, max_length=11),
        ),
        ops.AddField(
            model_name='Booking',
            name='external_uid',
            field=fields.CharField(null=True, max_length=512),
        ),
        ops.AddConstraint(
            model_name='Booking',
            constraint=UniqueConstraint(fields=('property_id', 'channel', 'external_uid'), name=None),
        ),
    ]
