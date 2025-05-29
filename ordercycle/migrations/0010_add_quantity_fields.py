# ordercycle/migrations/0010_add_quantity_fields.py

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('ordercycle', '0009_picklistdispatchstatus_complete_orders_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='picklistskuvalidation',
            name='required_quantity',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='picklistskuvalidation',
            name='validated_quantity',
            field=models.IntegerField(default=0),
        ),
    ]