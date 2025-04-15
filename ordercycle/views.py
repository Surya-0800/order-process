from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import render, redirect, get_object_or_404
from rest_framework.response import Response
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from rest_framework import status, viewsets
from django.shortcuts import render
from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Q
from django.conf.urls.static import static
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from django.db.models import Count
from django.db.models import Count, Q, Subquery, OuterRef
import os,re
import fitz  # PyMuPDF for reading PDF text
from .models import PDFUpload,AmazonOrders,FlipkarOrders,FirstcryOrders
from .serializers import PDFUploadSerializer
from collections import defaultdict
from PyPDF2 import PdfReader, PdfWriter
from .read_pdf_helper import extract_text_from_first_page
from process.flipkart_process import csv_to_dataframe as flipkart_csv_to_dt,grab_required_fields as flipkar_grab_fields,split_pdf_custom
from process.firstcry_process import excel_to_dataframe,grab_required_fields as firstcry_grab_fields,split_pdf_by_orderid as firstcry_split_pdf_by_order_id
from process.amazon_process import txt_to_dataframe,grab_required_fields,split_pdf_by_orderid
from .models import Picklist, PicklistItem, MasterTable, Picker, PicklistItemLocation,UserProfile
import tempfile
import shutil
from django.shortcuts import render
from django.http import Http404


# Home Page View
def home(request):
    return render(request, 'upload_pdf.html')

def location_orders_view(request):
    """View for the location-based order processing page"""
    return render(request, 'location_orders.html')

class PDFUploadViewSet(viewsets.ModelViewSet):
    queryset = PDFUpload.objects.all()
    serializer_class = PDFUploadSerializer
    parser_classes = (MultiPartParser, FormParser)

    def create(self, request, *args, **kwargs):
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
    
    @action(detail=False, methods=['post'])
    def process_files(self, request):
        """
        Process PDF and data files without permanent storage
        """
        pdf_file = request.FILES.get('pdf_file')
        data_file = request.FILES.get('data_file')
        
        if not pdf_file or not data_file:
            return Response(
                {'error': 'Both PDF and data files are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        results = {
            'flipkart_processed': 0,
            'amazon_processed': 0,
            'firstcry_processed': 0,
            'errors': []
        }
        
        try:
            # Save files to temp directory
            pdf_path = os.path.join(temp_dir, pdf_file.name)
            data_path = os.path.join(temp_dir, data_file.name)
            
            with open(pdf_path, 'wb') as f:
                for chunk in pdf_file.chunks():
                    f.write(chunk)
            
            with open(data_path, 'wb') as f:
                for chunk in data_file.chunks():
                    f.write(chunk)
            
            # Process PDF based on platform
            try:
                # Extract text from first page to identify platform
                text = extract_text_from_first_page(pdf_path)

                if "E-Kart Logistics" in text or "flipkart" in text.lower():
                  df = flipkart_csv_to_dt(data_path)
                  final_output_dict = flipkar_grab_fields(df.to_dict(orient="records"))
                  firstcry_data = split_pdf_custom(pdf_path, r"C:\Users\teja0\Downloads\Order Process Cycle-20250403T030855Z-001\Order Process Cycle\orderCycleProject\media\flipkartPdfs", final_output_dict) 
                  for order_number, order_data in firstcry_data.items():
                      order_type = "Single"
                      # The second element (index 1) contains the list of items
                      items = order_data[0]
                      if len(items) >1:
                          order_type = "Multiple"
                      
                      # The fourth element (index 3) contains output_pdf_location
                      pdf_info = order_data[-1]
                      
                      pdf_url = pdf_info.get('output_pdf_location', '')
                      
                      for item in items:
                          qty = int(item["Qty"])
                          if qty >1:
                              order_type = "Multiple"
                          FlipkarOrders.objects.create(
                              order_number=order_number,
                              order_type = order_type,
                              sku=item['sku'].replace("\n", ""),
                              quantity=qty,
                              pdf_url=pdf_url
                          )
                      results['flipkart_processed'] += 1
                    
                elif "FirstCry" in text:
                  df = excel_to_dataframe(data_path)
                  final_output_dict = firstcry_grab_fields(df.to_dict(orient="records"))
                  firstcry_data = firstcry_split_pdf_by_order_id(pdf_path, "/home/surya/code/mycode/Order Process Cycle/orderCycleProject/firstcryPdfs", final_output_dict) 
                  for order_number, order_data in firstcry_data.items():
                      order_type = "Single"
                      # The second element (index 1) contains the list of items
                      items = order_data[1]
                      if len(items) >1:
                          order_type = "Multiple"
                      
                      # The fourth element (index 3) contains output_pdf_location
                      pdf_info = order_data[-1]
                      
                      pdf_url = pdf_info.get('output_pdf_location', '')
                      
                      for item in items:
                          qty = int(item["Qty"])
                          if qty >1:
                              order_type = "Multiple"
                          FirstcryOrders.objects.create(
                              order_number=order_number,
                              order_type = order_type,
                              sku=item['sku'].replace("\n", ""),
                              quantity=qty,
                              pdf_url=pdf_url
                          )
                      results['firstcry_processed'] += 1

                elif "amazon" in text.lower():
                    # Process data file to get mapping info
                    df = txt_to_dataframe(data_path)
                    final_output_dict = grab_required_fields(df.to_dict(orient="records"))
                    amazon_data = split_pdf_by_orderid(pdf_path, r"C:\Users\teja0\Downloads\Order Process Cycle-20250403T030855Z-001\Order Process Cycle\orderCycleProject\media\amazonPdfs", final_output_dict)
                    for order_number, order_data in amazon_data.items():
                      order_type = "Single"
                      # The second element (index 1) contains the list of items
                      items = order_data[1]
                      if len(items) >1:
                          order_type = "Multiple"
                      
                      # The fourth element (index 3) contains output_pdf_location
                      pdf_info = order_data[-1]
                      
                      pdf_url = pdf_info.get('output_pdf_location', '')
                      print(items)
                      for item in items:
                          qty = int(item["Qty"])
                          if qty >1:
                              order_type = "Multiple"
                          AmazonOrders.objects.create(
                              order_number=order_number,
                              order_type = order_type,
                              sku=item['sku'].replace("\n", ""),
                              quantity=qty,
                              pdf_url=pdf_url,
                              AWB=item["AWB"]
                          )
                      
                      results['amazon_processed'] += 1
                
                else:
                    results['errors'].append(f"Unknown platform for {pdf_file.name}")
                    
            except Exception as e:
                print(results)
                print("==============================================================")
                import traceback
                print(traceback.format_exc())
                import pdb; pdb.set_trace()
                results['errors'].append(f"Error processing {pdf_file.name}: {str(e)}")
                
        finally:
            # Clean up temporary files
            shutil.rmtree(temp_dir)
        
        return Response({
            'status': 'success',
            'message': 'Files processed successfully',
            'results': results
        })
    

class OrderCountsViewSet(ViewSet):
    @action(detail=False, methods=['get'])
    def get_counts(self, request):
        # Get status from query params, default to 'Ready to Process'
        status = request.query_params.get('status', 'Ready to Process')
        
        # Initialize counts dictionary
        counts = {
            'AMAZON': {'total': 0, 'single': 0, 'multi': 0},
            'FLIPKART': {'total': 0, 'single': 0, 'multi': 0},
            'FIRSTCRY': {'total': 0, 'single': 0, 'multi': 0},
            'MEESHO': {'total': 0, 'single': 0, 'multi': 0}
        }

        # Filter by status for all platforms
        # Amazon orders
        amazon_orders = AmazonOrders.objects.filter(status=status)
        counts['AMAZON']['total'] = amazon_orders.values('order_number').distinct().count()
        counts['AMAZON']['single'] = amazon_orders.filter(order_type='Single').values('order_number').distinct().count()
        counts['AMAZON']['multi'] = amazon_orders.filter(order_type='Multiple').values('order_number').distinct().count()
            
        # Flipkart orders
        flipkart_orders = FlipkarOrders.objects.filter(status=status)
        counts['FLIPKART']['total'] = flipkart_orders.values('order_number').distinct().count()
        counts['FLIPKART']['single'] = flipkart_orders.filter(order_type='Single').values('order_number').distinct().count()
        counts['FLIPKART']['multi'] = flipkart_orders.filter(order_type='Multiple').values('order_number').distinct().count()
            
        # FirstCry orders
        firstcry_orders = FirstcryOrders.objects.filter(status=status)
        counts['FIRSTCRY']['total'] = firstcry_orders.values('order_number').distinct().count()
        counts['FIRSTCRY']['single'] = firstcry_orders.filter(order_type='Single').values('order_number').distinct().count()
        counts['FIRSTCRY']['multi'] = firstcry_orders.filter(order_type='Multiple').values('order_number').distinct().count()
        
        return Response(counts)

    @action(detail=False, methods=['get'])
    def get_single_orders(self, request):
        """
        Get detailed list of single orders
        """
        platform = request.query_params.get('platform', '').upper()
        batch_limit = request.query_params.get('batch_limit', None)
        status = request.query_params.get('status', 'Ready to Process')
        
        # Initialize data as an empty list by default
        data = []
        
        if platform == 'AMAZON':
            # Get single orders based on order_type field and include only distinct order numbers
            single_orders = AmazonOrders.objects.filter(
                order_type='Single', 
                status=status
            ).order_by('order_number').distinct('order_number')
            
            # Serialize the data
            data = [{
                'order_number': order.order_number,
                'sku': order.sku,
                'quantity': order.quantity,
                'pdf_url': order.pdf_url
            } for order in single_orders]

        elif platform == 'FLIPKART':
            # Get single orders based on order_type field and include only distinct order numbers
            single_orders = FlipkarOrders.objects.filter(
                order_type='Single',
                status=status
            ).order_by('order_number').distinct('order_number')
            
            # Serialize the data
            data = [{
                'order_number': order.order_number,
                'sku': order.sku,
                'quantity': order.quantity,
                'pdf_url': order.pdf_url
            } for order in single_orders]
        
        elif platform == 'FIRSTCRY':
            # Get single orders based on order_type field and include only distinct order numbers
            single_orders = FirstcryOrders.objects.filter(
                order_type='Single',
                status=status
            ).order_by('order_number').distinct('order_number')
            
            # Serialize the data
            data = [{
                'order_number': order.order_number,
                'sku': order.sku,
                'quantity': order.quantity,
                'pdf_url': order.pdf_url
            } for order in single_orders]
        
        # Apply batch limit if provided
        if batch_limit:
            try:
                batch_limit = int(batch_limit)
                data = data[:batch_limit]
            except (ValueError, TypeError):
                # If invalid batch_limit, return all records (no limit)
                pass
        
        return Response(data)

    @action(detail=False, methods=['get'])
    def get_multi_orders(self, request):
        """
        Get detailed list of multi orders
        """
        platform = request.query_params.get('platform', '').upper()
        batch_limit = request.query_params.get('batch_limit', None)
        status = request.query_params.get('status', 'Ready to Process')
        
        # Initialize data as an empty list by default
        data = []
        
        if platform == 'AMAZON':
            # Get multi orders based on order_type field and include only distinct order numbers
            multi_orders = AmazonOrders.objects.filter(
                order_type='Multiple',
                status=status
            ).order_by('order_number').distinct('order_number')
            
            # Serialize the data
            data = [{
                'order_number': order.order_number,
                'sku': order.sku,
                'quantity': order.quantity,
                'pdf_url': order.pdf_url
            } for order in multi_orders]

        elif platform == 'FLIPKART':
            # Get multi orders based on order_type field and include only distinct order numbers
            multi_orders = FlipkarOrders.objects.filter(
                order_type='Multiple',
                status=status
            ).order_by('order_number').distinct('order_number')
            
            # Serialize the data
            data = [{
                'order_number': order.order_number,
                'sku': order.sku,
                'quantity': order.quantity,
                'pdf_url': order.pdf_url
            } for order in multi_orders]

        elif platform == 'FIRSTCRY':
            # Get multi orders based on order_type field and include only distinct order numbers
            multi_orders = FirstcryOrders.objects.filter(
                order_type='Multiple',
                status=status
            ).order_by('order_number').distinct('order_number')
            
            # Serialize the data
            data = [{
                'order_number': order.order_number,
                'sku': order.sku,
                'quantity': order.quantity,
                'pdf_url': order.pdf_url
            } for order in multi_orders]
        
        # Apply batch limit if provided
        if batch_limit:
            try:
                batch_limit = int(batch_limit)
                data = data[:batch_limit]
            except (ValueError, TypeError):
                # If invalid batch_limit, return all records (no limit)
                pass
        
        return Response(data)

    @action(detail=False, methods=['post'])
    def process_orders(self, request):
        """
        Process selected orders with strict batch limit and SKU limit enforcement
        """
        try:
            # Get data from request
            orders = request.data.get('orders', [])
            batch_limit = request.data.get('batch_limit', 50)
            sku_limit = request.data.get('sku_limit', 0)  # Default to 0 (no limit) if not provided
            next_status = request.data.get('next_status', 'Pick')
            platform = request.data.get('platform', 'UNKNOWN').upper()
            order_type = request.data.get('order_type', 'SINGLE').upper()
            
            print(f"Processing orders: platform={platform}, order_type={order_type}, batch_limit={batch_limit}, sku_limit={sku_limit}")
            print(f"Total orders received: {len(orders)}")
            
            # Convert limits to integers
            try:
                batch_limit = int(batch_limit)
                sku_limit = int(sku_limit)
            except (ValueError, TypeError) as e:
                print(f"Error converting limits to int: {e}")
                batch_limit = 50
                sku_limit = 0
            
            # Validate limits
            if batch_limit <= 0:
                batch_limit = 50
            
            # Map order_type from uppercase SINGLE/MULTIPLE to the database format (Single/Multiple)
            db_order_type = 'Single' if order_type == 'SINGLE' else 'Multiple'
            
            # Get the appropriate model based on platform
            if platform == 'AMAZON':
                order_model = AmazonOrders
            elif platform == 'FLIPKART':
                order_model = FlipkarOrders
            elif platform == 'FIRSTCRY':
                order_model = FirstcryOrders
            else:
                # Handle unknown platform
                return Response({
                    'status': 'error',
                    'message': f'Unknown platform: {platform}'
                }, status=400)
            
            # Process orders in batches respecting both batch_limit and sku_limit
            processed_orders = []
            created_picklists = []
            
            # Fetch all ready-to-process orders from the provided list
            all_orders = []
            for order_id in orders:
                order = order_model.objects.filter(
                    order_number=order_id,
                    status='Ready to Process'
                ).first()
                
                if order:
                    all_orders.append(order)
            
            if not all_orders:
                return Response({
                    'status': 'error',
                    'message': 'No orders found with the specified criteria',
                }, status=404)
            
            # Process orders in batches, creating new picklists as needed
            remaining_orders = all_orders[:]
            
            while remaining_orders:
                # Create a new picklist for this batch
                picklist_id = Picklist.generate_picklist_id()
                picklist = Picklist.objects.create(
                    picklist_id=picklist_id,
                    picklist_type=order_type,
                    quantity=0,  # Will update after processing
                    platform=platform,
                    status='CREATED'
                )
                created_picklists.append(picklist_id)
                
                current_batch = []
                unique_skus = set()
                
                # Fill the current batch respecting both limits
                for order in remaining_orders[:]:
                    # Check if adding this order would exceed the SKU limit
                    if sku_limit > 0 and order.sku not in unique_skus and len(unique_skus) >= sku_limit:
                        # SKU limit would be exceeded, don't add this order to current batch
                        continue
                    
                    # Check if adding this order would exceed the batch limit
                    if len(current_batch) >= batch_limit:
                        # Batch limit reached, don't add more orders
                        break
                    
                    # Add this order to the current batch
                    current_batch.append(order)
                    unique_skus.add(order.sku)
                    remaining_orders.remove(order)
                
                # Process the current batch
                for order in current_batch:
                    # Update order status
                    order.status = next_status
                    order.save()
                    
                    # Create picklist item
                    PicklistItem.objects.create(
                        picklist=picklist,
                        order_number=order.order_number,
                        sku=order.sku,
                        quantity=order.quantity
                    )
                    
                    processed_orders.append(order.order_number)
                
                # Update picklist quantity
                if current_batch:
                    picklist.quantity = len(current_batch)
                    picklist.save()
                else:
                    # No orders were processed in this batch, delete the picklist
                    picklist.delete()
                    created_picklists.pop()  # Remove this picklist ID from the list
            
            if not processed_orders:
                return Response({
                    'status': 'error',
                    'message': 'No orders could be processed with the specified criteria',
                }, status=404)
            
            return Response({
                'status': 'success',
                'message': f'Processed {len(processed_orders)} {platform} orders across {len(created_picklists)} picklists',
                'processed_count': len(processed_orders),
                'total_count': len(orders),
                'batch_limit': batch_limit,
                'sku_limit': sku_limit,
                'processed_orders': processed_orders,
                'picklist_ids': created_picklists,
                'main_picklist_id': created_picklists[0] if created_picklists else None
            })
            
        except Exception as e:
            import traceback
            print(f"Error in process_orders: {str(e)}")
            traceback.print_exc()
            
            return Response({
                'status': 'error',
                'message': f'Error processing orders: {str(e)}',
            }, status=500)
class PicklistViewSet(ViewSet):
    @action(detail=False, methods=['get'])
    def get_picklists(self, request):
        """
        Get all picklists with optional status filter and sorted by status
        (CREATED first, then others) and then by created_at date
        """
        status = request.query_params.get('status', None)
        
        if status:
            picklists = Picklist.objects.filter(status=status)
        else:
            picklists = Picklist.objects.all()
        
        # Define a custom sorting order for statuses
        # This will ensure CREATED appears before PRINTED and other statuses
        status_order = {
            'CREATED': 1,
            'PRINTED': 2,
            'PACKING': 3,
            # Add other statuses as needed with appropriate numbers
        }
        
        # Convert queryset to list for custom sorting
        picklists_list = list(picklists)
        
        # Custom sorting: first by status order, then by created_at date (descending)
        picklists_list.sort(
            key=lambda p: (
                status_order.get(p.status, 999),  # Default to a high number for undefined statuses
                -p.created_at.timestamp()  # Negative timestamp for descending date order
            )
        )
        
        data = [{
            'picklist_id': picklist.picklist_id,
            'picklist_type': picklist.picklist_type,
            'quantity': picklist.quantity,
            'status': picklist.status,
            'platform': picklist.platform,
            'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for picklist in picklists_list]
        
        return Response(data)
    
    # Update this method in your PicklistViewSet class in views.py
    @action(detail=True, methods=['get'])
    def get_picklist_items(self, request, pk=None):
        """
        Get all items in a picklist with location information if available
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            items = picklist.items.all().prefetch_related('location_info')  # Use prefetch_related to optimize
            
            # Get all active pickers
            pickers = Picker.objects.filter(is_active=True).values('picker_id', 'name')
            
            # Get items with enhanced data
            detailed_items = []
            for item in items:
                # Get location info if available
                try:
                    location_info = getattr(item, 'location_info', None)
                    
                    if location_info:
                        location = location_info.location
                        picked = location_info.picked
                        picker_id = location_info.picker.picker_id if location_info.picker else None
                    else:
                        # Try to get location from MasterTable
                        master_item = MasterTable.objects.filter(sku=item.sku).first()
                        location = master_item.location if master_item else "Unknown"
                        picked = False
                        picker_id = None
                        
                        # Create location info if it doesn't exist but we have location data
                        if master_item and master_item.location:
                            location_info, created = PicklistItemLocation.objects.get_or_create(
                                picklist_item=item,
                                defaults={
                                    'location': master_item.location,
                                    'picked': False
                                }
                            )
                except Exception as e:
                    # If any error occurs, use default values
                    location = "Unknown"
                    picked = False
                    picker_id = None
                
                detailed_items.append({
                    'id': item.id,
                    'order_number': item.order_number,
                    'sku': item.sku,
                    'quantity': item.quantity,
                    'location': location,
                    'picked': picked,
                    'picker_id': picker_id
                })
            
            # Sort the items by SKU in descending order by default
            detailed_items.sort(key=lambda x: x['sku'], reverse=True)
            
            return Response({
                'picklist_id': picklist.picklist_id,
                'picklist_type': picklist.picklist_type,
                'status': picklist.status,
                'platform': picklist.platform,
                'items': detailed_items,
                'pickers': list(pickers),
                'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(picklist, 'created_at') else None
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)
        
    @action(detail=True, methods=['post'])
    def undo_picked(self, request, pk=None):
      """
      Undo picked status for items in a picklist
      """
      try:
          picklist = Picklist.objects.get(picklist_id=pk)
          item_ids = request.data.get('item_ids', [])
          
          if not item_ids:
              return Response({
                  'status': 'error',
                  'message': 'No items specified'
              }, status=400)
          
          # Update picked status for all specified items
          updated_count = 0
          
          for item_id in item_ids:
              try:
                  # Get the picklist item
                  item = PicklistItem.objects.get(id=item_id, picklist=picklist)
                  
                  # Get or create location info if it doesn't exist
                  location_info, created = PicklistItemLocation.objects.get_or_create(
                      picklist_item=item,
                      defaults={'location': 'Unknown', 'picked': False}
                  )
                  
                  # Set picked to False
                  location_info.picked = False
                  location_info.picked_at = None  # Clear the picked timestamp
                  location_info.save()
                  
                  updated_count += 1
              except PicklistItem.DoesNotExist:
                  continue
          
          # Update picklist status if needed
          if picklist.status == 'PRINTED' or picklist.status == 'PACKING':
              # If at least one item is unpicked, change status back to CREATED
              picklist.status = 'CREATED'
              picklist.save()
          
          return Response({
              'status': 'success',
              'message': f'Unmarked {updated_count} items as picked. Picklist status set to CREATED.'
          })
      
      except Picklist.DoesNotExist:
          return Response({
              'status': 'error',
              'message': 'Picklist not found'
          }, status=404)
          

    @action(detail=True, methods=['post'])
    def mark_picked(self, request, pk=None):
        """
        Mark items in a picklist as picked
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            order_numbers = request.data.get('order_numbers', [])
            
            if not order_numbers:
                return Response({
                    'status': 'error',
                    'message': 'No orders specified'
                }, status=400)
            
            # Mark items as picked
            updated_count = PicklistItem.objects.filter(
                picklist=picklist,
                order_number__in=order_numbers
            ).update(picked=True)
            
            # Check if all items are picked
            if picklist.items.filter(picked=False).count() == 0:
                picklist.status = 'PACKING'
                picklist.save()
                
                return Response({
                    'status': 'success',
                    'message': f'All items marked as picked. Picklist moved to PACKING status.'
                })
            else:
                return Response({
                    'status': 'success',
                    'message': f'{updated_count} items marked as picked'
                })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)
        
    @action(detail=True, methods=['get'])
    def get_detailed_items(self, request, pk=None):
        """
        Get detailed picklist items with location information
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            items = picklist.items.all().select_related('location_info')
            
            # Get all active pickers
            pickers = Picker.objects.filter(is_active=True).values('picker_id', 'name')
            
            # Get items with location data
            detailed_items = []
            for item in items:
                location_info = getattr(item, 'location_info', None)
                
                # Try to get location from MasterTable if not available
                location = "Unknown"
                picked = False
                picker_id = None
                
                if location_info:
                    location = location_info.location
                    picked = location_info.picked
                    picker_id = location_info.picker.picker_id if location_info.picker else None
                else:
                    # Try to get location from MasterTable
                    try:
                        master_item = MasterTable.objects.filter(sku=item.sku).first()
                        if master_item:
                            location = master_item.location
                            
                            # Create location info if it doesn't exist
                            location_info, created = PicklistItemLocation.objects.get_or_create(
                                picklist_item=item,
                                defaults={'location': location, 'picked': False}
                            )
                    except Exception as e:
                        print(f"Error finding location: {e}")
                
                detailed_items.append({
                    'id': item.id,
                    'order_number': item.order_number,
                    'sku': item.sku,
                    'quantity': item.quantity,
                    'location': location,
                    'picked': picked,
                    'picker_id': picker_id
                })
            
            return Response({
                'picklist_id': picklist.picklist_id,
                'picklist_type': picklist.picklist_type,
                'status': picklist.status,
                'platform': picklist.platform,
                'items': detailed_items,
                'pickers': list(pickers)
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)

    @action(detail=True, methods=['post'])
    def assign_picker(self, request, pk=None):
        """
        Assign a picker to picklist items
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            picker_id = request.data.get('picker_id')
            item_ids = request.data.get('item_ids', [])
            
            if not picker_id:
                return Response({
                    'status': 'error',
                    'message': 'Picker ID is required'
                }, status=400)
            
            try:
                picker = Picker.objects.get(picker_id=picker_id)
            except Picker.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': f'Picker with ID {picker_id} not found'
                }, status=404)
            
            # If no specific items provided, assign picker to all items
            if not item_ids:
                item_ids = list(picklist.items.values_list('id', flat=True))
            
            # Update location info for all specified items
            updated_count = 0
            for item_id in item_ids:
                try:
                    item = PicklistItem.objects.get(id=item_id, picklist=picklist)
                    
                    # Get or create location info
                    location_info, created = PicklistItemLocation.objects.get_or_create(
                        picklist_item=item,
                        defaults={'location': 'Unknown', 'picked': False}
                    )
                    
                    # Assign picker
                    location_info.picker = picker
                    location_info.save()
                    updated_count += 1
                    
                except PicklistItem.DoesNotExist:
                    continue
            
            return Response({
                'status': 'success',
                'message': f'Assigned picker {picker_id} to {updated_count} items'
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)
        
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
      """
    Update the status of a picklist
    """
      try:
          picklist = Picklist.objects.get(picklist_id=pk)
          new_status = request.data.get('status')
          
          if not new_status:
              return Response({
                  'status': 'error',
                  'message': 'No status specified'
              }, status=400)
          
          # Update the picklist status
          old_status = picklist.status
          picklist.status = new_status
          picklist.save()
          
          return Response({
              'status': 'success',
              'message': f'Picklist status updated from {old_status} to {new_status}'
          })
      
      except Picklist.DoesNotExist:
          return Response({
              'status': 'error',
              'message': 'Picklist not found'
          }, status=404)

    @action(detail=True, methods=['post'])
    def mark_items_picked(self, request, pk=None):
        """
        Mark picklist items as picked
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            item_ids = request.data.get('item_ids', [])
            
            if not item_ids:
                return Response({
                    'status': 'error',
                    'message': 'No items specified'
                }, status=400)
            
            # Update picked status for all specified items
            updated_count = 0
            for item_id in item_ids:
                try:
                    item = PicklistItem.objects.get(id=item_id, picklist=picklist)
                    
                    # Get or create location info
                    location_info, created = PicklistItemLocation.objects.get_or_create(
                        picklist_item=item,
                        defaults={'location': 'Unknown', 'picked': False}
                    )
                    
                    # Mark as picked
                    location_info.picked = True
                    location_info.picked_at = timezone.now()
                    location_info.save()
                    updated_count += 1
                    
                except PicklistItem.DoesNotExist:
                    continue
            
            # Check if all items are picked (for information only)
            all_picked = not PicklistItemLocation.objects.filter(
                picklist_item__picklist=picklist, 
                picked=False
            ).exists()
            
            # We're not changing the status to PRINTED here anymore
            # This will be handled by the print button
            
            return Response({
                'status': 'success',
                'message': f'Marked {updated_count} items as picked',
                'all_picked': all_picked
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)
            

# Add these imports at the top of your views file
from django.db.models import Count, F, Value, CharField
from django.db.models.functions import Concat
from django.shortcuts import get_object_or_404

# Add this ViewSet to handle location-based order processing
class LocationOrdersViewSet(viewsets.ViewSet):
    """
    API for location-based order processing
    """
    
    @action(detail=False, methods=['get'])
    def location_counts(self, request):
        """
        Get order counts by location including unknown locations
        """
        platform = request.query_params.get('platform', 'AMAZON')
        order_type = request.query_params.get('order_type', 'single')
        status = request.query_params.get('status', 'Ready to Process')
        
        # Determine which model to use based on platform
        if platform.upper() == 'AMAZON':
            order_model = AmazonOrders
        elif platform.upper() == 'FLIPKART':
            order_model = FlipkarOrders
        elif platform.upper() == 'FIRSTCRY':
            order_model = FirstcryOrders
        else:
            return Response({
                'error': f'Unknown platform: {platform}'
            }, status=400)
        
        # Filter by order type and status
        db_order_type = 'Single' if order_type.lower() == 'single' else 'Multiple'
        orders = order_model.objects.filter(
            order_type=db_order_type,
            status=status
        )
        
        # Get all SKUs in orders
        all_order_skus = list(orders.values_list('sku', flat=True))
        
        # Get known SKUs from MasterTable
        known_skus = MasterTable.objects.filter(
            sku__in=all_order_skus
        ).values_list('sku', flat=True).distinct()
        
        # Get unknown SKUs (not in MasterTable)
        unknown_skus = set(all_order_skus) - set(known_skus)
        
        # Join with MasterTable to get locations
        # We'll use a subquery for each SKU
        location_data = {}
        
        # Process known locations
        for order in orders:
            # Find the location(s) for this SKU
            locations = MasterTable.objects.filter(sku=order.sku)
            
            if locations.exists():
                for loc in locations:
                    if loc.location not in location_data:
                        location_data[loc.location] = {
                            'count': 1,
                            'order_ids': [order.order_number]
                        }
                    else:
                        location_data[loc.location]['count'] += 1
                        if order.order_number not in location_data[loc.location]['order_ids']:
                            location_data[loc.location]['order_ids'].append(order.order_number)
            else:
                # Add to "Unknown" location
                if "Unknown" not in location_data:
                    location_data["Unknown"] = {
                        'count': 1,
                        'order_ids': [order.order_number]
                    }
                else:
                    location_data["Unknown"]['count'] += 1
                    if order.order_number not in location_data["Unknown"]['order_ids']:
                        location_data["Unknown"]['order_ids'].append(order.order_number)
        
        # Format the response
        response_data = {
            'total_orders': orders.count(),
            'locations': []
        }
        
        for location, data in location_data.items():
            response_data['locations'].append({
                'location': location,
                'count': data['count'],
                'order_count': len(data['order_ids'])
            })
        
        # Sort by count descending
        response_data['locations'] = sorted(
            response_data['locations'], 
            key=lambda x: x['count'], 
            reverse=True
        )
        
        return Response(response_data)
    


    @action(detail=False, methods=['get'])
    def orders_by_location(self, request):
        """
        Get orders for specific locations, including unknown locations
        """
        platform = request.query_params.get('platform', 'AMAZON')
        order_type = request.query_params.get('order_type', 'single')
        status = request.query_params.get('status', 'Ready to Process')
        locations = request.query_params.getlist('locations', [])
        include_unknown = request.query_params.get('include_unknown', 'true').lower() == 'true'
        
        # Determine which model to use based on platform
        if platform.upper() == 'AMAZON':
            order_model = AmazonOrders
        elif platform.upper() == 'FLIPKART':
            order_model = FlipkarOrders
        elif platform.upper() == 'FIRSTCRY':
            order_model = FirstcryOrders
        else:
            return Response({
                'error': f'Unknown platform: {platform}'
            }, status=400)
        
        # Filter by order type and status
        db_order_type = 'Single' if order_type.lower() == 'single' else 'Multiple'
        orders = order_model.objects.filter(
            order_type=db_order_type,
            status=status
        )
        
        # Find all SKUs in the specified locations
        skus_in_locations = MasterTable.objects.filter(
            location__in=locations
        ).values_list('sku', flat=True).distinct()
        
        # Get all SKUs in orders
        all_order_skus = orders.values_list('sku', flat=True).distinct()
        
        # Get SKUs that exist in orders but not in MasterTable or with unknown locations
        if include_unknown:
            known_skus = MasterTable.objects.filter(
                sku__in=all_order_skus
            ).values_list('sku', flat=True).distinct()
            
            unknown_skus = set(all_order_skus) - set(known_skus)
        else:
            unknown_skus = set()
        
        # Filter orders to include those with SKUs in specified locations or unknown locations
        if locations or include_unknown:
            # If locations are specified or include_unknown is true
            filtered_orders = orders.filter(
                Q(sku__in=skus_in_locations) | Q(sku__in=unknown_skus)
            )
        else:
            # Include all orders if no filters are applied
            filtered_orders = orders
        
        # Prepare the response
        result = []
        for order in filtered_orders:
            # Get locations for this order's SKU if available
            sku_locations = MasterTable.objects.filter(sku=order.sku)
            location_info = []
            
            if sku_locations.exists():
                # SKU has known locations
                for loc in sku_locations:
                    location_info.append({
                        'location': loc.location,
                        'box_no': loc.box_no,
                        'selected': loc.location in locations
                    })
            else:
                # SKU has unknown location
                location_info.append({
                    'location': "Unknown",
                    'box_no': "",
                    'selected': include_unknown
                })
            
            result.append({
                'order_number': order.order_number,
                'sku': order.sku,
                'quantity': order.quantity,
                'locations': location_info
            })
        
        # Sort by location (prioritizing selected locations)
        def location_sort_key(order):
            # First sort by whether any location is selected
            has_selected = any(loc['selected'] for loc in order['locations'])
            # Then by the first selected location if any
            selected_location = next((loc['location'] for loc in order['locations'] if loc['selected']), "ZZZZZ")
            return (not has_selected, selected_location)
        
        result = sorted(result, key=location_sort_key)
        
        return Response(result)
    @action(detail=False, methods=['post'])
    def process_location_orders(self, request):
        """
        Process orders from specific locations with batch and SKU limits
        """
        try:
            # Get data from request
            platform = request.data.get('platform', 'UNKNOWN').upper()
            order_type = request.data.get('order_type', 'SINGLE').upper()
            locations = request.data.get('locations', [])
            include_unknown = request.data.get('include_unknown', True)
            batch_limit = request.data.get('batch_limit', 50)
            sku_limit = request.data.get('sku_limit', 0)
            next_status = request.data.get('next_status', 'Pick')
            
            # Validate inputs
            if not locations and not include_unknown:
                return Response({
                    'status': 'error',
                    'message': 'No locations specified and unknown locations not included'
                }, status=400)
            
            # Convert limits to integers
            try:
                batch_limit = int(batch_limit)
                sku_limit = int(sku_limit)
            except (ValueError, TypeError) as e:
                batch_limit = 50
                sku_limit = 0
            
            # Determine the order model based on platform
            if platform == 'AMAZON':
                order_model = AmazonOrders
            elif platform == 'FLIPKART':
                order_model = FlipkarOrders
            elif platform == 'FIRSTCRY':
                order_model = FirstcryOrders
            else:
                return Response({
                    'status': 'error',
                    'message': f'Unknown platform: {platform}'
                }, status=400)
            
            # Get orders for the specified locations
            db_order_type = 'Single' if order_type == 'SINGLE' else 'Multiple'
            
            # Find all SKUs in the specified locations
            skus_in_locations = MasterTable.objects.filter(
                location__in=locations
            ).values_list('sku', flat=True).distinct()
            
            # Get all SKUs in orders
            all_order_skus = order_model.objects.filter(
                order_type=db_order_type,
                status='Ready to Process'
            ).values_list('sku', flat=True).distinct()
            
            # Get SKUs that exist in orders but not in MasterTable
            if include_unknown:
                known_skus = MasterTable.objects.filter(
                    sku__in=all_order_skus
                ).values_list('sku', flat=True).distinct()
                
                unknown_skus = set(all_order_skus) - set(known_skus)
            else:
                unknown_skus = set()
            
            # Get orders with these SKUs
            orders = order_model.objects.filter(
                order_type=db_order_type,
                status='Ready to Process'
            ).filter(Q(sku__in=skus_in_locations) | Q(sku__in=unknown_skus))
            
            if not orders.exists():
                return Response({
                    'status': 'error',
                    'message': 'No orders found with the specified criteria',
                }, status=404)
            
            # Process orders in batches respecting both batch_limit and sku_limit
            processed_orders = []
            created_picklists = []
            
            all_orders = list(orders)
            remaining_orders = all_orders[:]
            
            while remaining_orders:
                # Create a new picklist for this batch
                picklist_id = Picklist.generate_picklist_id()
                picklist = Picklist.objects.create(
                    picklist_id=picklist_id,
                    picklist_type=order_type,
                    quantity=0,  # Will update after processing
                    platform=platform,
                    status='CREATED'
                )
                created_picklists.append(picklist_id)
                
                current_batch = []
                unique_skus = set()
                
                # Fill the current batch respecting both limits
                for order in remaining_orders[:]:
                    # Check if adding this order would exceed the SKU limit
                    if sku_limit > 0 and order.sku not in unique_skus and len(unique_skus) >= sku_limit:
                        # SKU limit would be exceeded, don't add this order to current batch
                        continue
                    
                    # Check if adding this order would exceed the batch limit
                    if len(current_batch) >= batch_limit:
                        # Batch limit reached, don't add more orders
                        break
                    
                    # Add this order to the current batch
                    current_batch.append(order)
                    unique_skus.add(order.sku)
                    remaining_orders.remove(order)
                
                # Process the current batch
                for order in current_batch:
                    # Update order status
                    order.status = next_status
                    order.save()
                    
                    # Create picklist item
                    PicklistItem.objects.create(
                        picklist=picklist,
                        order_number=order.order_number,
                        sku=order.sku,
                        quantity=order.quantity
                    )
                    
                    processed_orders.append(order.order_number)
                
                # Update picklist quantity
                if current_batch:
                    picklist.quantity = len(current_batch)
                    picklist.save()
                else:
                    # No orders were processed in this batch, delete the picklist
                    picklist.delete()
                    created_picklists.pop()
            
            if not processed_orders:
                return Response({
                    'status': 'error',
                    'message': 'No orders could be processed with the specified criteria',
                }, status=404)
            
            return Response({
                'status': 'success',
                'message': f'Processed {len(processed_orders)} {platform} orders across {len(created_picklists)} picklists',
                'processed_count': len(processed_orders),
                'total_count': len(orders),
                'batch_limit': batch_limit,
                'sku_limit': sku_limit,
                'locations': locations,
                'include_unknown': include_unknown,
                'processed_orders': processed_orders,
                'picklist_ids': created_picklists,
                'main_picklist_id': created_picklists[0] if created_picklists else None
            })
        
        except Exception as e:
            import traceback
            print(f"Error in process_location_orders: {str(e)}")
            traceback.print_exc()
            
            return Response({
                'status': 'error',
                'message': f'Error processing orders: {str(e)}',
            }, status=500)


def picklist_detail_view(request, picklist_id):
    """
    Render the picklist details page
    """
    try:
        # Check if picklist exists
        picklist = Picklist.objects.get(picklist_id=picklist_id)
        
        # Get all active pickers
        pickers = Picker.objects.filter(is_active=True)
        
        context = {
            'picklist_id': picklist_id,
            'pickers': pickers,
        }
        
        return render(request, 'picklist_detail.html', context)
    except Picklist.DoesNotExist:
        raise Http404("Picklist does not exist")

# Add to PicklistViewSet

def picklist_detail_view(request, picklist_id):
    """
    Render the picklist details page with barcode capabilities
    """
    try:
        # Check if picklist exists
        picklist = Picklist.objects.get(picklist_id=picklist_id)
        
        # Get all active pickers
        pickers = Picker.objects.filter(is_active=True)
        
        context = {
            'picklist_id': picklist_id,
            'pickers': pickers,
            # Add barcode library CSS/JS resources to template context
            'include_barcode_library': True,
        }
        
        return render(request, 'picklist_detail.html', context)
    except Picklist.DoesNotExist:
        raise Http404("Picklist does not exist")
    
from django.shortcuts import render
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_http_methods
import json

@require_http_methods(["GET"])
def get_picklist_barcode(request, picklist_id):
    """
    API endpoint to generate barcode data for a picklist
    This could be used as an alternative to client-side barcode generation
    """
    try:
        # Check if picklist exists
        picklist = Picklist.objects.get(picklist_id=picklist_id)
        
        # Return barcode data - could be generated server-side if needed
        # For now we're just confirming the picklist exists
        return JsonResponse({
            'status': 'success',
            'picklist_id': picklist_id,
            'message': 'Picklist exists and barcode data is available'
        })
    except Picklist.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Picklist not found'
        }, status=404)


def pack_stage_view(request):
    """
    Render the packing stage page
    """
    return render(request, 'pack_stage.html')

@require_http_methods(["GET"])
def search_picklist(request):
    """
    Search for a picklist by ID
    """
    picklist_id = request.GET.get('picklist_id', '')
    if not picklist_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Picklist ID is required'
        }, status=400)
    
    try:
        # Get picklist with PACKING status (this is correct)
        picklist = Picklist.objects.get(picklist_id=picklist_id, status='PACKING')
        
        # Get picklist items with their details
        items = PicklistItem.objects.filter(picklist=picklist).select_related('location_info')
        
        items_data = []
        for item in items:
            # Get location info if available
            location = "Unknown"
            
            # FIX: Default picked status to False instead of using the location_info.picked value
            # This ensures items start as "not packed" in the packing stage
            picked = False
            
            picker_id = None
            
            if hasattr(item, 'location_info'):
                location = item.location_info.location
                # We're intentionally NOT using item.location_info.picked here
                # Because in the packing stage, we want to start fresh
                
                # Only use the picker ID from location_info
                picker_id = item.location_info.picker.picker_id if item.location_info.picker else None
            
            items_data.append({
                'id': item.id,
                'order_number': item.order_number,
                'sku': item.sku,
                'quantity': item.quantity,
                'location': location,
                'picked': picked,  # Always False for packing stage
                'picker_id': picker_id
            })
        
        return JsonResponse({
            'status': 'success',
            'picklist': {
                'picklist_id': picklist.picklist_id,
                'picklist_type': picklist.picklist_type,
                'quantity': picklist.quantity,
                'status': picklist.status,
                'platform': picklist.platform,
                'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'items': items_data
            }
        })
    
    except Picklist.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': f'Picklist with ID {picklist_id} not found or not in PACKING status'
        }, status=404)

@require_http_methods(["GET"])
def search_product(request):
    """
    Search for a product by product ID
    """
    product_id = request.GET.get('product_id', '')
    
    if not product_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Product ID is required'
        }, status=400)
    
    try:
        # Find the product in the master table
        product = MasterTable.objects.filter(product_id=product_id).first()
        
        if not product:
            return JsonResponse({
                'status': 'error',
                'message': f'Product with ID {product_id} not found'
            }, status=404)
        
        # Return product details
        return JsonResponse({
            'status': 'success',
            'product': {
                'sku': product.sku,
                'image_url': product.image_url or '',
                'location': product.location,
                'product_id': product.product_id,
                'box_no': product.box_no or '',
                'mrp': float(product.mrp) if product.mrp else 0,
                'generic_name': product.generic_name or '',
                'pack_check': product.pack_check or '',
                'pack_remarks': product.pack_remarks or ''
            }
        })
    
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error searching for product: {str(e)}'
        }, status=500)

@require_http_methods(["POST"])
def mark_picklist_completed(request, picklist_id):
    """
    Mark a picklist as completed
    """
    try:
        # Print request details for debugging
        print("Headers:", request.headers)
        print("CSRF Token:", request.META.get('HTTP_X_CSRFTOKEN', 'Not provided'))
        
        picklist = get_object_or_404(Picklist, picklist_id=picklist_id, status='PACKING')
        
        # Update the picklist status to COMPLETED
        picklist.status = 'COMPLETED'
        picklist.save()
        
        return JsonResponse({
            'status': 'success',
            'message': f'Picklist {picklist_id} marked as completed'
        })
    
    except Exception as e:
        print(f"Error completing picklist: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Error marking picklist as completed: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
def mark_product_packed(request):
    """
    Mark a product as packed in a picklist
    """
    try:
        data = json.loads(request.body)
        picklist_id = data.get('picklist_id')
        sku = data.get('sku')
        
        if not picklist_id or not sku:
            return JsonResponse({
                'status': 'error',
                'message': 'Picklist ID and SKU are required'
            }, status=400)
        
        # Find the picklist
        picklist = get_object_or_404(Picklist, picklist_id=picklist_id, status='PACKING')
        
        # Find all items with the matching SKU in this picklist
        items = PicklistItem.objects.filter(picklist=picklist, sku=sku)
        
        if not items.exists():
            return JsonResponse({
                'status': 'error',
                'message': f'No items with SKU {sku} found in picklist {picklist_id}'
            }, status=404)
        
        # Track items that were successfully packed
        packed_items = 0
        
        # Mark all matching items as packed
        for item in items:
            # First update the PicklistItem table
            item.picked = True
            item.save()
            
            # Also update PicklistItemLocation if it exists
            try:
                location_info, created = PicklistItemLocation.objects.get_or_create(
                    picklist_item=item,
                    defaults={'location': 'Unknown', 'picked': False}
                )
                location_info.picked = True
                location_info.picked_at = timezone.now()
                location_info.save()
            except Exception as e:
                print(f"Error updating location info: {str(e)}")
                # Continue anyway - the PicklistItem is already updated
            
            packed_items += 1
        
        # Check if all items are now packed by looking at PicklistItem model
        # This fixes the issue where we were using location_info.picked
        all_packed = not PicklistItem.objects.filter(picklist=picklist, picked=False).exists()
        
        return JsonResponse({
            'status': 'success',
            'message': f'Items with SKU {sku} marked as packed ({packed_items} items)',
            'all_packed': all_packed
        })
    
    except Exception as e:
        print(f"Error in mark_product_packed: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Error marking product as packed: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def search_product(request):
    """
    Search for a product by product ID
    """
    product_id = request.GET.get('product_id', '')
    
    if not product_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Product ID is required'
        }, status=400)
    
    try:
        # Find the product in the master table
        product = MasterTable.objects.filter(product_id=product_id).first()
        
        if not product:
            return JsonResponse({
                'status': 'error',
                'message': f'Product with ID {product_id} not found'
            }, status=404)
        
        # Construct the image path based on product ID
        image_path = f"/media/ASINWISEIMAGES/{product_id}.jpg"
        
        # Check if the file exists (optional, but helpful)
        import os
        from django.conf import settings
        
        full_image_path = os.path.join(settings.MEDIA_ROOT, "ASINWISEIMAGES", f"{product_id}.jpg")
        if not os.path.exists(full_image_path):
            # If image doesn't exist, use a default "not found" image
            image_path = "/static/images/no_image_found.jpg"
        
        # Return product details
        return JsonResponse({
            'status': 'success',
            'product': {
                'sku': product.sku,
                'image_url': image_path,
                'location': product.location,
                'product_id': product.product_id,
                'box_no': product.box_no or '',
                'mrp': float(product.mrp) if product.mrp else 0,
                'generic_name': product.generic_name or '',
                'pack_check': product.pack_check or '',
                'pack_remarks': product.pack_remarks or ''
            }
        })
    
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error searching for product: {str(e)}'
        }, status=500)
    
@require_http_methods(["POST"])
def print_order_label(request):
    """
    Find and return the PDF URL for a specific order, properly handling file paths
    and converting them to accessible URLs for frontend printing
    """
    try:
        data = json.loads(request.body)
        platform = data.get('platform')
        order_number = data.get('order_number')
        include_file_path = data.get('include_file_path', False)  # New parameter
        
        if not platform or not order_number:
            return JsonResponse({
                'status': 'error',
                'message': 'Platform and order number are required'
            }, status=400)
        
        # Get the appropriate model based on platform
        if platform.upper() == 'AMAZON':
            order = AmazonOrders.objects.filter(order_number=order_number).first()
        elif platform.upper() == 'FLIPKART':
            order = FlipkarOrders.objects.filter(order_number=order_number).first()
        elif platform.upper() == 'FIRSTCRY':
            order = FirstcryOrders.objects.filter(order_number=order_number).first()
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Unknown platform: {platform}'
            }, status=400)
        
        if not order:
            return JsonResponse({
                'status': 'error',
                'message': f'Order {order_number} not found'
            }, status=404)
        
        # Get the PDF path from the order
        pdf_path = order.pdf_url
        
        if not pdf_path:
            return JsonResponse({
                'status': 'error',
                'message': f'No PDF file found for order {order_number}'
            }, status=404)
        
        # Print debug info
        print(f"DEBUG: Original PDF path from database: {pdf_path}")
            
        # Handle file system paths vs URL paths
        import os
        from django.conf import settings
        
        # Variable to store the actual file path for later
        actual_file_path = None
        
        # Case 1: If it's a full file system path (Windows or Unix)
        if pdf_path.startswith('C:') or pdf_path.startswith('/'):
            # Get just the filename from the path
            filename = os.path.basename(pdf_path)
            print(f"DEBUG: Extracted filename: {filename}")
            
            # Determine which directory it belongs to based on platform
            if platform.upper() == 'AMAZON':
                pdf_url = f'amazonPdfs/{filename}'
            elif platform.upper() == 'FLIPKART':
                pdf_url = f'flipkartPdfs/{filename}'
            elif platform.upper() == 'FIRSTCRY':
                pdf_url = f'firstcryPdfs/{filename}'
            else:
                pdf_url = f'orderPdfs/{filename}'
            
            print(f"DEBUG: Target media URL path: {pdf_url}")
                
            # Check if the file exists in the target media location
            media_path = os.path.join(settings.MEDIA_ROOT, pdf_url.replace('/', os.path.sep).lstrip('/'))
            print(f"DEBUG: Full media path: {media_path}")
            
            # Save this for the response
            actual_file_path = media_path

            if actual_file_path and 'media/media' in actual_file_path:
                actual_file_path = actual_file_path.replace('media/media', 'media')
                print(f"DEBUG: Fixed duplicate media in path: {actual_file_path}")
            
            # If the file doesn't exist in media directory, we need to copy it there
            if not os.path.exists(media_path):
                print(f"DEBUG: Media path doesn't exist, attempting to copy")
                
                # Ensure the directory exists
                target_dir = os.path.dirname(media_path)
                os.makedirs(target_dir, exist_ok=True)
                print(f"DEBUG: Created directory: {target_dir}")
                
                # Only copy if source file exists
                if os.path.exists(pdf_path):
                    print(f"DEBUG: Source file exists at {pdf_path}, copying to {media_path}")
                    import shutil
                    shutil.copy2(pdf_path, media_path)
                    
                    # Verify the copy
                    if os.path.exists(media_path):
                        print(f"DEBUG: File successfully copied, size: {os.path.getsize(media_path)} bytes")
                    else:
                        print(f"DEBUG: File copy failed, destination file doesn't exist")
                else:
                    print(f"DEBUG: Source file NOT found at {pdf_path}")
                    
                    # Check for alternate locations
                    alternate_path = None
                    
                    # Try to find the file in the existing media directories
                    for root_dir in [settings.MEDIA_ROOT]:
                        for dirpath, dirnames, filenames in os.walk(root_dir):
                            if filename in filenames:
                                alternate_path = os.path.join(dirpath, filename)
                                print(f"DEBUG: Found file in alternate location: {alternate_path}")
                                break
                        if alternate_path:
                            break
                    
                    if alternate_path:
                        print(f"DEBUG: Copying from alternate location: {alternate_path} to {media_path}")
                        shutil.copy2(alternate_path, media_path)
                        actual_file_path = media_path
                    else:
                        return JsonResponse({
                            'status': 'error',
                            'message': f'PDF file not found at {pdf_path}'
                        }, status=404)
            else:
                print(f"DEBUG: File already exists at {media_path}, size: {os.path.getsize(media_path)} bytes")
        # Case 2: It's already a relative URL path
        else:
            pdf_url = pdf_path
            print(f"DEBUG: Using existing relative URL: {pdf_url}")
            
            # Ensure it starts with a slash for URL formatting
            if not pdf_url.startswith('/'):
                pdf_url = '/' + pdf_url
                print(f"DEBUG: Added leading slash: {pdf_url}")
            
            # Try to determine the file path based on the URL
            if pdf_url.startswith('/media/'):
                path_part = pdf_url.lstrip('/media/')
                possible_path = os.path.join(settings.MEDIA_ROOT, path_part)
                if os.path.exists(possible_path):
                    actual_file_path = possible_path
                    print(f"DEBUG: Found actual file at: {actual_file_path}")
        
        # Convert to absolute URL
        from django.contrib.sites.shortcuts import get_current_site
        current_site = get_current_site(request)
        domain = current_site.domain
        print(f"DEBUG: Domain from site: {domain}")
        protocol = 'https' if request.is_secure() else 'http'
        
        if pdf_url.startswith('/'):
            # If pdf_url starts with a slash, just concatenate normally
            absolute_url = f"{protocol}://{domain}{pdf_url}"
        else:
            # If pdf_url doesn't start with a slash, add one between domain and path
            absolute_url = f"{protocol}://{domain}/media/{pdf_url}"
        
        print(f"DEBUG: Final absolute URL: {absolute_url}")
        
        # Check if the URL is actually accessible - this is important for debugging
        import urllib.request
        import urllib.error
        
        try:
            # Try with a HEAD request to see if the file exists
            req = urllib.request.Request(absolute_url, method='HEAD')
            response = urllib.request.urlopen(req, timeout=3)
            print(f"DEBUG: URL is accessible: {absolute_url}, status: {response.status}")
        except urllib.error.HTTPError as e:
            print(f"DEBUG: URL is NOT accessible: {absolute_url}, error: {e.code} {e.reason}")
        except Exception as e:
            print(f"DEBUG: Error checking URL: {str(e)}")
        
        # Prepare the response
        response_data = {
            'status': 'success',
            'pdf_url': absolute_url,
            'order_number': order.order_number,
            'awb': getattr(order, 'AWB', 'N/A'),
            'platform': platform
        }
        
        # Include the direct file path if requested
        if include_file_path and actual_file_path and os.path.exists(actual_file_path):
            response_data['file_path'] = actual_file_path
            print(f"DEBUG: Including file path in response: {actual_file_path}")
        
        return JsonResponse(response_data)
    
    except Exception as e:
        import traceback
        print(f"Error in print_order_label: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error processing print request: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def get_printer_list(request):
    """
    Return a list of available printers from the system
    Note: This is just a placeholder endpoint since QZ Tray manages printer discovery client-side
    """
    # This endpoint is mainly for API completeness
    # QZ Tray handles printer discovery on the client side
    return JsonResponse({
        'status': 'success',
        'message': 'QZ Tray will detect printers client-side'
    })

@require_http_methods(["POST"])
def save_printer_preferences(request):
    """
    Save user's printer preferences
    """
    try:
        data = json.loads(request.body)
        selected_printer = data.get('printer_name')
        is_default = data.get('is_default', False)
        
        if not selected_printer:
            return JsonResponse({
                'status': 'error',
                'message': 'Printer name is required'
            }, status=400)
        
        # If user is logged in, store preference in their profile
        if request.user.is_authenticated:
            # Assuming you have a UserProfile model with printer_preference field
            # If not, you can create one or use Django session
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            profile.printer_preference = selected_printer
            profile.save()
            
            return JsonResponse({
                'status': 'success',
                'message': f'Printer preference saved: {selected_printer}'
            })
        else:
            # For anonymous users, store in session
            request.session['printer_preference'] = selected_printer
            return JsonResponse({
                'status': 'success',
                'message': f'Printer preference saved in session: {selected_printer}'
            })
            
    except Exception as e:
        import traceback
        print(f"Error in save_printer_preferences: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error saving printer preferences: {str(e)}'
        }, status=500)

@require_http_methods(["GET"])
def get_printer_preferences(request):
    """
    Get user's saved printer preferences
    """
    try:
        preference = None
        
        # If user is logged in, get from profile
        if request.user.is_authenticated:
            # Assuming you have a UserProfile model with printer_preference field
            profile = UserProfile.objects.filter(user=request.user).first()
            if profile and profile.printer_preference:
                preference = profile.printer_preference
        
        # If not found or user not logged in, try session
        if not preference:
            preference = request.session.get('printer_preference')
        
        return JsonResponse({
            'status': 'success',
            'preference': preference
        })
            
    except Exception as e:
        import traceback
        print(f"Error in get_printer_preferences: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error getting printer preferences: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
def send_test_print(request):
    """
    Send a test print to a specific printer
    This API just returns success - actual printing happens client-side with QZ Tray
    """
    try:
        data = json.loads(request.body)
        printer_name = data.get('printer_name')
        
        if not printer_name:
            return JsonResponse({
                'status': 'error',
                'message': 'Printer name is required'
            }, status=400)
        
        # For this endpoint, we don't actually send a print job from the server
        # QZ Tray handles printing client-side
        # This endpoint is just for API completeness and logging
        
        print(f"Test print requested for printer: {printer_name}")
        
        return JsonResponse({
            'status': 'success',
            'message': f'Test print initiated for {printer_name}'
        })
            
    except Exception as e:
        import traceback
        print(f"Error in send_test_print: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error initiating test print: {str(e)}'
        }, status=500)

@require_http_methods(["GET"])
def search_awb(request):
    """
    Search for an order by AWB number
    """
    awb = request.GET.get('awb', '').strip()
    
    if not awb:
        return JsonResponse({
            'status': 'error',
            'message': 'AWB number is required'
        }, status=400)
    
    # Search across all platforms
    amazon_order = AmazonOrders.objects.filter(AWB=awb).first()
    flipkart_order = FlipkarOrders.objects.filter(AWB=awb).first()
    firstcry_order = FirstcryOrders.objects.filter(AWB=awb).first()
    
    order = amazon_order or flipkart_order or firstcry_order
    
    if not order:
        return JsonResponse({
            'status': 'error',
            'message': f'No order found with AWB {awb}'
        }, status=404)
    
    # Determine the platform
    if amazon_order:
        platform = 'AMAZON'
    elif flipkart_order:
        platform = 'FLIPKART'
    else:
        platform = 'FIRSTCRY'
    
    return JsonResponse({
        'status': 'success',
        'order': {
            'order_number': order.order_number,
            'sku': order.sku,
            'platform': platform,
            'pdf_url': order.pdf_url,
            'awb': order.AWB
        }
    })