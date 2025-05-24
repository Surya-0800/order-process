import os
import tempfile
import pandas as pd
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from ordercycle.models import MasterTable
from ordercycle.api.serializers import FileUploadSerializer

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def import_master_data_api(request):
    """
    API endpoint to import master data from Excel file
    """
    serializer = FileUploadSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(
            {'status': 'error', 'message': 'Invalid file', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    uploaded_file = serializer.validated_data['file']
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        temp_file_path = temp_file.name
    
    try:
        result = process_excel_file(temp_file_path)
        return Response(result, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response(
            {'status': 'error', 'message': f'Import failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

def process_excel_file(file_path):
    """
    Process Excel file and import data into MasterTable
    """
    # Read Excel file
    df = pd.read_excel(file_path, sheet_name=0)
    
    # Check required columns
    expected_columns = ['SKU', 'IMAGE URL', 'LOCATION', 'PRODUCT ID', 'BOX NO', 
                       'MRP', 'GENERIC NAME', 'PACK CHECK', 'PACK REMARKS']
    
    missing_columns = [col for col in expected_columns if col not in df.columns]
    if missing_columns:
        return {
            'status': 'error',
            'message': f"Missing columns: {', '.join(missing_columns)}",
            'created_count': 0,
            'updated_count': 0,
            'skipped_count': 0,
            'error_count': 0,
            'errors': [f"Available columns: {', '.join(df.columns)}"]
        }
    
    # Initialize counters
    created_count = 0
    updated_count = 0
    error_count = 0
    skipped_count = 0
    errors = []
    
    # Process data in transaction
    with transaction.atomic():
        for index, row in df.iterrows():
            try:
                # Extract and validate required fields
                sku = str(row['SKU']).strip() if pd.notna(row['SKU']) else None
                location = str(row['LOCATION']).strip() if pd.notna(row['LOCATION']) else None
                
                # Skip if SKU or location is missing
                if not sku or not location or sku == 'nan' or location == 'nan':
                    skipped_count += 1
                    continue
                
                # Extract optional fields
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
                
                # Create or update the item
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
                else:
                    updated_count += 1
            
            except Exception as e:
                error_count += 1
                errors.append(f'Row {index+2}: {str(e)}')
    
    return {
        'status': 'success',
        'message': f'Import completed: Created {created_count}, Updated {updated_count}, Skipped {skipped_count}, Errors {error_count}',
        'created_count': created_count,
        'updated_count': updated_count, 
        'skipped_count': skipped_count,
        'error_count': error_count,
        'errors': errors[:10]  # Limit to first 10 errors
    }

# Dashboard view
def master_data_dashboard(request):
    """
    HTML dashboard for master data import
    """
    return render(request, 'master_data_dashboard.html')

@csrf_exempt
def import_master_data_ajax(request):
    """
    AJAX endpoint for dashboard file upload
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'})
    
    if 'file' not in request.FILES:
        return JsonResponse({'status': 'error', 'message': 'No file uploaded'})
    
    uploaded_file = request.FILES['file']
    
    # Validate file
    if not uploaded_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'status': 'error', 'message': 'Only Excel files are allowed'})
    
    # Save temporarily and process
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        temp_file_path = temp_file.name
    
    try:
        result = process_excel_file(temp_file_path)
        return JsonResponse(result)
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Import failed: {str(e)}'})
    
    finally:
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)