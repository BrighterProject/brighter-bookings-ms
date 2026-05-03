from tortoise import migrations
from tortoise.migrations import operations as ops
from app.models import BookingStatus
from uuid import uuid4
from tortoise import fields

class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name='Booking',
            fields=[
                ('id', fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('property_id', fields.UUIDField()),
                ('property_owner_id', fields.UUIDField()),
                ('user_id', fields.UUIDField()),
                ('start_date', fields.DateField()),
                ('end_date', fields.DateField()),
                ('status', fields.CharEnumField(default=BookingStatus.PENDING, description='PENDING: pending\nCONFIRMED: confirmed\nCOMPLETED: completed\nCANCELLED: cancelled\nNO_SHOW: no_show', enum_type=BookingStatus, max_length=9)),
                ('price_per_night', fields.DecimalField(max_digits=8, decimal_places=2)),
                ('total_price', fields.DecimalField(max_digits=10, decimal_places=2)),
                ('currency', fields.CharField(default='EUR', max_length=3)),
                ('num_guests', fields.IntField(default=1)),
                ('guest_name', fields.CharField(null=True, max_length=255)),
                ('guest_email', fields.CharField(null=True, max_length=255)),
                ('guest_phone', fields.CharField(null=True, max_length=50)),
                ('guest_country', fields.CharField(null=True, max_length=2)),
                ('special_requests', fields.TextField(null=True, unique=False)),
                ('gap_adjustment_pct', fields.DecimalField(default=0, max_digits=5, decimal_places=2)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ],
            options={'table': 'bookings', 'app': 'models', 'pk_attr': 'id'},
            bases=['AbstractModel'],
        ),
    ]
