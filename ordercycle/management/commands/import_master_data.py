# yourapp/management/commands/import_master_data.py
import os
import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from ordercycle.models import MasterTable  # Updated to use MasterTable

class Command(BaseCommand):
    help = 'Import master table data from Excel file into the database'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the Excel file')

    def handle(self, *args, **options):
        file_path = options['file_path']

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        self.stdout.write(self.style.SUCCESS(f'Reading file: {file_path}'))

        try:
            # Read only the first sheet of the Excel file
            df = pd.read_excel(file_path, sheet_name=0)
            
            # Display Excel info
            self.stdout.write(f'Excel file has {len(df)} rows and {len(df.columns)} columns')
            self.stdout.write(f'Columns: {list(df.columns)}')
            
            # Check if all required columns exist
            expected_columns = ['SKU', 'IMAGE URL', 'LOCATION', 'PRODUCT ID', 'BOX NO', 
                               'MRP', 'GENERIC NAME', 'PACK CHECK', 'PACK REMARKS']
            
            missing_columns = [col for col in expected_columns if col not in df.columns]
            if missing_columns:
                self.stdout.write(self.style.ERROR(
                    f"Missing columns: {', '.join(missing_columns)}. "
                    f"Available columns: {', '.join(df.columns)}"
                ))
                return
            
            # Statistics
            created_count = 0
            updated_count = 0
            error_count = 0
            skipped_count = 0

            # Process the data in a transaction
            with transaction.atomic():
                # Process each row
                for index, row in df.iterrows():
                    try:
                        # Extract data with exact column names
                        sku = str(row['SKU']).strip() if pd.notna(row['SKU']) else None
                        location = str(row['LOCATION']).strip() if pd.notna(row['LOCATION']) else None
                        
                        # Skip if SKU or location is missing
                        if not sku or not location or sku == 'nan' or location == 'nan':
                            skipped_count += 1
                            continue
                        
                        # Get optional fields
                        image_url = str(row['IMAGE URL']).strip() if pd.notna(row['IMAGE URL']) else None
                        product_id = str(row['PRODUCT ID']).strip() if pd.notna(row['PRODUCT ID']) else None
                        box_no = str(row['BOX NO']).strip() if pd.notna(row['BOX NO']) else None
                        
                        # Convert MRP to decimal
                        mrp = None
                        if pd.notna(row['MRP']):
                            try:
                                mrp = float(row['MRP'])
                            except (ValueError, TypeError):
                                mrp = None
                        
                        generic_name = str(row['GENERIC NAME']).strip() if pd.notna(row['GENERIC NAME']) else None
                        pack_check = str(row['PACK CHECK']).strip() if pd.notna(row['PACK CHECK']) else None
                        pack_remarks = str(row['PACK REMARKS']).strip() if pd.notna(row['PACK REMARKS']) else None
                        
                        # Create or update the item in MasterTable
                        item, created = MasterTable.objects.update_or_create(
                            sku=sku,
                            location=location,
                            defaults={
                                'image_url': image_url,
                                'product_id': product_id,
                                'box_no': box_no,
                                'mrp': mrp,
                                'generic_name': generic_name,
                                'pack_check': pack_check,
                                'pack_remarks': pack_remarks,
                            }
                        )
                        
                        if created:
                            created_count += 1
                            if created_count % 100 == 0:
                                self.stdout.write(f'Created {created_count} items so far...')
                        else:
                            updated_count += 1
                    
                    except Exception as e:
                        error_count += 1
                        self.stdout.write(self.style.ERROR(f'Error on row {index+2}: {str(e)}'))
            
            # Final report
            self.stdout.write(self.style.SUCCESS(
                f'Import completed: Created {created_count}, Updated {updated_count}, '
                f'Skipped {skipped_count}, Errors {error_count}'
            ))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Import failed: {str(e)}'))