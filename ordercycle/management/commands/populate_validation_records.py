from django.core.management.base import BaseCommand
from django.db import transaction
from ordercycle.models import Picklist, PicklistItem, PicklistSKUValidation, MasterTable


class Command(BaseCommand):
    help = 'Populate missing PicklistSKUValidation records for existing picklists'

    def add_arguments(self, parser):
        parser.add_argument(
            '--picklist-id',
            type=str,
            help='Specific picklist ID to process (optional)',
        )
        parser.add_argument(
            '--status',
            type=str,
            default='PACKING',
            help='Picklist status to process (default: PACKING)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating records',
        )

    def handle(self, *args, **options):
        picklist_id = options.get('picklist_id')
        status = options.get('status')
        dry_run = options.get('dry_run')

        if dry_run:
            self.stdout.write(
                self.style.WARNING('🏃‍♂️ DRY RUN MODE - No records will be created')
            )

        # Filter picklists
        if picklist_id:
            picklists = Picklist.objects.filter(picklist_id=picklist_id)
            if not picklists.exists():
                self.stdout.write(
                    self.style.ERROR(f'❌ Picklist {picklist_id} not found')
                )
                return
        else:
            picklists = Picklist.objects.filter(status=status)

        total_created = 0
        total_updated = 0
        total_picklists = picklists.count()

        self.stdout.write(f'📦 Processing {total_picklists} picklist(s)...')

        for picklist in picklists:
            self.stdout.write(f'\n📋 Processing picklist: {picklist.picklist_id}')
            
            # Get all picklist items
            picklist_items = PicklistItem.objects.filter(picklist=picklist)
            items_count = picklist_items.count()
            
            if items_count == 0:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠️  No items found in picklist {picklist.picklist_id}')
                )
                continue

            self.stdout.write(f'  📊 Found {items_count} items')

            created_count = 0
            updated_count = 0

            if not dry_run:
                with transaction.atomic():
                    for item in picklist_items:
                        # Get product_id from master table
                        product = MasterTable.objects.filter(sku=item.sku).first()
                        product_id = product.product_id if product else None

                        # Get or create validation record
                        validation_record, created = PicklistSKUValidation.objects.get_or_create(
                            picklist=picklist,
                            sku=item.sku,
                            order_number=item.order_number,
                            defaults={
                                'validated': False,
                                'quantity': item.quantity,
                                'validated_count': 0,
                                'product_id': product_id
                            }
                        )

                        if created:
                            created_count += 1
                            if created_count <= 3:  # Show first 3
                                self.stdout.write(f'    ✅ Created: {item.sku} - {item.order_number}')
                        else:
                            # Update existing record if needed
                            update_needed = False
                            if validation_record.quantity != item.quantity:
                                validation_record.quantity = item.quantity
                                update_needed = True
                                
                            if not validation_record.product_id and product_id:
                                validation_record.product_id = product_id
                                update_needed = True
                                
                            # Recalculate validated status
                            new_validated_status = validation_record.validated_count >= validation_record.quantity
                            if validation_record.validated != new_validated_status:
                                validation_record.validated = new_validated_status
                                update_needed = True

                            if update_needed:
                                validation_record.save()
                                updated_count += 1
                                if updated_count <= 3:  # Show first 3
                                    self.stdout.write(f'    🔄 Updated: {item.sku} - {item.order_number}')
            else:
                # Dry run - just check what would be created
                for item in picklist_items:
                    exists = PicklistSKUValidation.objects.filter(
                        picklist=picklist,
                        sku=item.sku,
                        order_number=item.order_number
                    ).exists()
                    
                    if not exists:
                        created_count += 1
                        if created_count <= 5:  # Show first 5 in dry run
                            self.stdout.write(f'    📝 Would create: {item.sku} - {item.order_number}')

            if created_count > 3:
                self.stdout.write(f'    ... and {created_count - 3} more created')
            if updated_count > 3:
                self.stdout.write(f'    ... and {updated_count - 3} more updated')

            self.stdout.write(
                self.style.SUCCESS(f'  ✅ Created: {created_count}, Updated: {updated_count}')
            )
            
            total_created += created_count
            total_updated += updated_count

        # Summary
        self.stdout.write(f'\n📊 SUMMARY:')
        self.stdout.write(
            self.style.SUCCESS(f'  🆕 Total records created: {total_created}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'  🔄 Total records updated: {total_updated}')
        )
        
        if dry_run and (total_created > 0 or total_updated > 0):
            self.stdout.write(
                self.style.WARNING(f'\n▶️  Run without --dry-run to actually create the records:')
            )
            if picklist_id:
                self.stdout.write(f'    python manage.py populate_validation_records --picklist-id {picklist_id}')
            else:
                self.stdout.write(f'    python manage.py populate_validation_records')
        elif not dry_run and total_created == 0 and total_updated == 0:
            self.stdout.write(
                self.style.SUCCESS(f'  🎉 All validation records already exist and are up to date!')
            )