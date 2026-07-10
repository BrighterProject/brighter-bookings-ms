from tortoise import migrations
from tortoise.migrations import operations as ops
from app.fields import EncryptedCharField
from app.models import DocumentType, Gender
from tortoise.fields.base import OnDelete
from uuid import uuid4
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0001_initial')]

    initial = False

    operations = [
        ops.CreateModel(
            name='GuestIdentity',
            fields=[
                ('id', fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('booking', fields.ForeignKeyField('models.Booking', source_field='booking_id', db_constraint=True, to_field='id', related_name='guest_identities', on_delete=OnDelete.CASCADE)),
                ('first_name', fields.CharField(max_length=100)),
                ('middle_name', fields.CharField(null=True, max_length=100)),
                ('last_name', fields.CharField(max_length=100)),
                ('date_of_birth', fields.DateField(null=True)),
                ('gender', fields.CharEnumField(null=True, description='MALE: male\nFEMALE: female\nOTHER: other', enum_type=Gender, max_length=6)),
                ('citizenship', fields.CharField(null=True, max_length=2)),
                ('document_type', fields.CharEnumField(null=True, description='ID_CARD: id_card\nPASSPORT: passport', enum_type=DocumentType, max_length=8)),
                ('document_number', EncryptedCharField(null=True, max_length=512)),
                ('document_issuing_country', fields.CharField(null=True, max_length=2)),
                ('pin_egn', EncryptedCharField(null=True, max_length=512)),
            ],
            options={'table': 'guest_identities', 'app': 'models', 'pk_attr': 'id'},
            bases=['AbstractModel'],
        ),
        ops.AddField(
            model_name='Booking',
            name='checkin_link_sent_at',
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        ),
        ops.AddField(
            model_name='Booking',
            name='guest_data_purged_at',
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        ),
        ops.AddField(
            model_name='Booking',
            name='payment_method',
            field=fields.CharField(null=True, max_length=20),
        ),
    ]
