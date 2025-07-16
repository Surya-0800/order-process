"""
Views for handling PDF uploads and processing.
"""
import os
import shutil
import tempfile
import logging
import traceback
from django.conf import settings
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.decorators import action

from ..models import PDFUpload, AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders
# Import the serializer directly from api module to avoid circular imports
from ..api.serializers import PDFUploadSerializer
from ..utils.pdf_helpers import extract_text_from_first_page

# Import processing modules
from process.flipkart_process import csv_to_dataframe as flipkart_csv_to_dt, grab_required_fields as flipkar_grab_fields, split_pdf_custom
from process.firstcry_process import excel_to_dataframe, grab_required_fields as firstcry_grab_fields, split_pdf_by_orderid as firstcry_split_pdf_by_order_id
from process.amazon_process import txt_to_dataframe, grab_required_fields, split_pdf_by_orderid
from process.meesho_process import excel_to_dataframe as meesho_excel_to_df, grab_required_fields as meesho_grab_fields, split_pdf_custom as meesho_split_pdf_custom

class PDFUploadViewSet(viewsets.ModelViewSet):
    """ViewSet for managing PDF uploads."""
    queryset = PDFUpload.objects.all()
    serializer_class = PDFUploadSerializer
    parser_classes = (MultiPartParser, FormParser)

    def create(self, request, *args, **kwargs):
        """Create a new PDF upload record."""
        file_serializer = PDFUploadSerializer(data=request.data)
        if file_serializer.is_valid():
            file_instance = file_serializer.save()
            return Response({
                "id": file_instance.id,
                "title": file_instance.title,
                "file": file_instance.file.url,
                "message": "File uploaded successfully"
            }, status=201)
        return Response(file_serializer.errors, status=400)
    
    @action(detail=False, methods=['post'],url_path='process-files')
    def process_files(self, request):
        """
        Process PDF and data files without permanent storage.
        
        This method handles:
        - Reading PDF and optional data files
        - Determining the e-commerce platform
        - Splitting PDFs by order
        - Creating order records in the database
        """
        pdf_file = request.FILES.get('pdf_file')
        data_file = request.FILES.get('data_file')
        
        if not pdf_file:
            return Response(
                {'error': 'PDF file is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        results = {
            'flipkart_processed': 0,
            'amazon_processed': 0,
            'firstcry_processed': 0,
            'meesho_processed': 0,
            'errors': []
        }
        
        try:
            # Save files to temp directory
            pdf_path = os.path.join(temp_dir, pdf_file.name)
            if data_file:
                data_path = os.path.join(temp_dir, data_file.name)
                with open(data_path, 'wb') as f:
                    for chunk in data_file.chunks():
                        f.write(chunk)
            
            with open(pdf_path, 'wb') as f:
                for chunk in pdf_file.chunks():
                    f.write(chunk)
            
            # Process PDF based on platform
            try:
                # Extract text from first page to identify platform
                text = extract_text_from_first_page(pdf_path)
                
                # Get the media root path from settings
                media_root = settings.MEDIA_ROOT

                # Process based on identified platform
                if "E-Kart Logistics" in text or "flipkart" in text.lower():
                    self._process_flipkart_pdf(pdf_path, data_path if data_file else None, media_root, results)
                    
                elif "FirstCry" in text:
                    self._process_firstcry_pdf(pdf_path, data_path if data_file else None, media_root, results)

                elif "amazon" in text.lower():
                    self._process_amazon_pdf(pdf_path, data_path if data_file else None, media_root, results)

                elif "CustomerAddress" in text or "Customer Address" in text:
                    self._process_meesho_pdf(pdf_path, data_path if data_file else None, media_root, results)
                
                else:
                    logging.error(f"Unknown platform for {pdf_file.name}")
                    results['errors'].append(f"Unknown platform for {pdf_file.name}")
                    
            except Exception as e:
                logging.error(f"Error processing {pdf_file.name}: {str(e)}")
                logging.error(traceback.format_exc())
                results['errors'].append(f"Error processing {pdf_file.name}: {str(e)}")
                
        finally:
            # Clean up temporary files
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
        
        return Response({
            'status': 'success',
            'message': 'Files processed successfully',
            'results': results
        })
    
    def _process_flipkart_pdf(self, pdf_path, data_path, media_root, results):
        """Process Flipkart PDFs and create order records."""
        flipkart_output_dir = os.path.join(media_root, 'flipkartPdfs')
        os.makedirs(flipkart_output_dir, exist_ok=True)
        
        if data_path:
            df = flipkart_csv_to_dt(data_path)
            final_output_dict = flipkar_grab_fields(df.to_dict(orient="records"))
        else:
            final_output_dict = []
            
        flipkart_data = split_pdf_custom(pdf_path, flipkart_output_dir, final_output_dict) 
        
        for order_number, order_data in flipkart_data.items():
            order_type = "Single"
            # The first element (index 0) contains the list of items
            items = order_data[0]
            if len(items) > 1:
                order_type = "Multiple"
            
            # The last element contains output_pdf_location
            pdf_info = order_data[-1]
            pdf_url = pdf_info.get('output_pdf_location', '')
            
            for item in items:
                qty = int(item["Qty"])
                if qty > 1:
                    order_type = "Multiple"
                FlipkarOrders.objects.update_or_create(
                    order_number=order_number,
                    sku=item['sku'].replace("\n", ""),
                    defaults={
                        'order_type': order_type,
                        'quantity': qty,
                        'pdf_url': pdf_url,
                        'AWB': item["AWB"]
                    }
                )
            results['flipkart_processed'] += 1
    
    def _process_firstcry_pdf(self, pdf_path, data_path, media_root, results):
        """Process FirstCry PDFs and create order records."""
        firstcry_output_dir = os.path.join(media_root, 'firstcryPdfs')
        os.makedirs(firstcry_output_dir, exist_ok=True)
        
        if data_path:
            df = excel_to_dataframe(data_path)
            final_output_dict = firstcry_grab_fields(df.to_dict(orient="records"))
        else:
            final_output_dict = []
            
        firstcry_data = firstcry_split_pdf_by_order_id(pdf_path, firstcry_output_dir, final_output_dict) 
        
        for order_number, order_data in firstcry_data.items():
            order_type = "Single"
            # The second element (index 1) contains the list of items
            items = order_data[1]
            if len(items) > 1:
                order_type = "Multiple"
            
            # The last element contains output_pdf_location
            pdf_info = order_data[-1]
            pdf_url = pdf_info.get('output_pdf_location', '')
            for item in items:
                  for i in item.keys():
                      if "Qty" in i :
                          qty = int(item[i])
                  if qty > 1:
                      order_type = "Multiple"
                  if not FirstcryOrders.objects.filter(order_number=order_number, sku=item['sku'].replace("\n", "")).exists():
                    FirstcryOrders.objects.update_or_create(
                        # These are the fields to match on (unique identifier)
                        order_number=order_number,
                        sku=item['sku'].replace("\n", ""),
                        
                        # These are the fields to update if record exists, or create if it doesn't
                        defaults={
                            'order_type': order_type,
                            'quantity': qty,
                            'pdf_url': pdf_url,
                            'AWB': item["shipment_id"]  # Note: FirstCry uses shipment_id for AWB
                        }
                    )
                    results['firstcry_processed'] += 1
                    print(results['firstcry_processed'])
    
    def _process_amazon_pdf(self, pdf_path, data_path, media_root, results):
        """Process Amazon PDFs and create order records."""
        amazon_output_dir = os.path.join(media_root, 'amazonPdfs')
        os.makedirs(amazon_output_dir, exist_ok=True)
        is_data_exists = False
        if data_path:
            is_data_exists = True
            df = txt_to_dataframe(data_path)
            final_output_dict = grab_required_fields(df.to_dict(orient="records"))
        else:
            final_output_dict = []
            
        amazon_data = split_pdf_by_orderid(pdf_path, amazon_output_dir, final_output_dict,is_data_exists)
        
        for order_number, order_data in amazon_data.items():
            order_type = "Single"
            # The second element (index 1) contains the list of items
            items = order_data[1]
            if len(items) > 1:
                order_type = "Multiple"
            
            # The last element contains output_pdf_location
            pdf_info = order_data[-1]
            # pdf_url = pdf_info.get('output_pdf_location', '')
            
            for item in items:
                qty = int(item["Qty"])
                if qty > 1:
                    order_type = "Multiple"
                AmazonOrders.objects.update_or_create(
                    order_number=order_number,
                    sku=item['sku'].replace("\n", ""),
                    
                    # These are the fields to update if record exists, or create if it doesn't
                    defaults={
                        'order_type': order_type,
                        'quantity': qty,
                        # 'pdf_url': pdf_url,  # Commented out as in original
                        'AWB': item["AWB"]
                    }
                )
            results['amazon_processed'] += 1
    
    def _process_meesho_pdf(self, pdf_path, data_path, media_root, results):
        """Process Meesho PDFs and create order records."""
        meesho_output_dir = os.path.join(media_root, 'meeshoPdfs')
        os.makedirs(meesho_output_dir, exist_ok=True)
        
        if data_path:
            df = meesho_excel_to_df(data_path)
            final_output_dict = meesho_grab_fields(df.to_dict(orient="records"))
        else:
            final_output_dict = []
            
        meesho_data = meesho_split_pdf_custom(pdf_path, meesho_output_dir, final_output_dict, top_ratio=0.413)
        
        for order_number, order_data in meesho_data.items():
            order_type = "Single"
            # The first element (index 0) contains the list of items
            items = order_data[0]
            if len(items) > 1:
                order_type = "Multiple"
            
            # The last element contains output_pdf_location
            pdf_info = order_data[-1]
            pdf_url = pdf_info.get('output_pdf_location', '')
            
            for item in items:
                qty = int(item["Qty"])
                if qty > 1:
                    order_type = "Multiple"
                MeeshoOrders.objects.update_or_create(
                order_number=order_number,
                sku=str(item['sku']).replace("\n", ""),
            
                defaults={
                    'order_type': order_type,
                    'quantity': qty,
                    'pdf_url': pdf_url,
                    'AWB': item["AWB"]
                }
            )
            results['meesho_processed'] += 1


# Add this to one of your view files
from django.http import JsonResponse
import os
from django.conf import settings

def check_pdf_path(request):
    """Debug view to check if PDF files exist"""
    file_path = request.GET.get('file_path', '')
    
    # Check absolute path if provided
    abs_exists = os.path.exists(file_path) if file_path.startswith('/') else False
    
    # Check relative path inside MEDIA_ROOT
    rel_path = file_path.replace(settings.MEDIA_URL, '')
    rel_file_path = os.path.join(settings.MEDIA_ROOT, rel_path)
    rel_exists = os.path.exists(rel_file_path)
    
    # Try other variations
    amazon_path = os.path.join(settings.MEDIA_ROOT, 'amazonPdfs', os.path.basename(file_path))
    amazon_exists = os.path.exists(amazon_path)
    
    return JsonResponse({
        'debug': True,
        'file_path': file_path,
        'absolute_path_exists': abs_exists,
        'media_root': settings.MEDIA_ROOT,
        'relative_path': rel_file_path,
        'relative_path_exists': rel_exists,
        'amazon_path': amazon_path,
        'amazon_path_exists': amazon_exists,
        'base_dir': str(settings.BASE_DIR),
        'media_url': settings.MEDIA_URL,
    })

from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from ordercycle.models import OrderPDF
@api_view(['GET'])
def download_pdf(request, order_id):
    """
    Download a PDF for a specific order
    """
    print("TRYINGGGG")
    # Get the order or return 404
    order = get_object_or_404(OrderPDF, order_id=order_id)
    
    # Check if the order has PDF content
    if not order.pdf_content:
        raise Http404("PDF not found for this order")
    
    # Create the HTTP response with the PDF content
    response = HttpResponse(order.pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{order.filename or f'Order_{order_id}.pdf'}"'
    
    return response