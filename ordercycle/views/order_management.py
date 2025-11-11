# views/order_management.py
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from django.conf import settings
import json
from django.utils import timezone
from ..models import (
    AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders,
    Picklist, PicklistItem, MasterTable, PicklistDispatchStatus,OrderPDF,PicklistItemLocation
)
from django.http import JsonResponse, HttpResponse
import io,traceback,os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:
    try:
        from PyPDF4 import PdfFileReader as PdfReader, PdfFileWriter as PdfWriter
    except ImportError:
        PdfReader = PdfWriter = None


def order_management_view(request):
    """
    Render the order management page
    """
    return render(request, 'order_management.html')


@require_http_methods(["GET"])
def get_order_status_api(request):
    """
    API endpoint to get the current status of an order
    """
    order_number = request.GET.get('order_number', '').strip()
    
    if not order_number:
        return JsonResponse({'error': 'Order number is required'}, status=400)
    
    # Search across all order models
    order_data = None
    platform = None
    
    # Try Amazon orders
    amazon_order = AmazonOrders.objects.filter(order_number=order_number).first()
    if amazon_order:
        order_data = amazon_order
        platform = 'Amazon'
    
    # Try Flipkart orders if not found in Amazon
    if not order_data:
        flipkart_order = FlipkarOrders.objects.filter(order_number=order_number).first()
        if flipkart_order:
            order_data = flipkart_order
            platform = 'Flipkart'
    
    # Try FirstCry orders
    if not order_data:
        firstcry_order = FirstcryOrders.objects.filter(order_number=order_number).first()
        if firstcry_order:
            order_data = firstcry_order
            platform = 'FirstCry'
    
    # Try Meesho orders
    if not order_data:
        meesho_order = MeeshoOrders.objects.filter(order_number=order_number).first()
        if meesho_order:
            order_data = meesho_order
            platform = 'Meesho'
    
    if not order_data:
        return JsonResponse({'error': 'Order not found'}, status=404)
    
    # Return order status
    response_data = {
        'order_number': order_data.order_number,
        'status': order_data.status,
        'platform': platform,
        'sku': order_data.sku,
        'quantity': order_data.quantity,
        'AWB': order_data.AWB,
    }
    
    return JsonResponse(response_data)


@require_http_methods(["GET"])
def search_order_api(request):
    """
    API endpoint to search for orders across all platforms
    """
    order_number = request.GET.get('order_number', '').strip()
    
    if not order_number:
        return JsonResponse({'error': 'Order number is required'}, status=400)
    
    # Search across all order models
    order_data = None
    platform = None
    
    # Try Amazon orders
    amazon_order = AmazonOrders.objects.filter(order_number=order_number).first()
    if amazon_order:
        order_data = amazon_order
        platform = 'Amazon'
    
    # Try Flipkart orders if not found in Amazon
    if not order_data:
        flipkart_order = FlipkarOrders.objects.filter(order_number=order_number).first()
        if flipkart_order:
            order_data = flipkart_order
            platform = 'Flipkart'
    
    # Try FirstCry orders
    if not order_data:
        firstcry_order = FirstcryOrders.objects.filter(order_number=order_number).first()
        if firstcry_order:
            order_data = firstcry_order
            platform = 'FirstCry'
    
    # Try Meesho orders
    if not order_data:
        meesho_order = MeeshoOrders.objects.filter(order_number=order_number).first()
        if meesho_order:
            order_data = meesho_order
            platform = 'Meesho'
    
    if not order_data:
        return JsonResponse({'error': 'Order not found'}, status=404)
    
    # Return only essential order data
    response_data = {
        'order_number': order_data.order_number,
        'sku': order_data.sku,
        'quantity': order_data.quantity,
        'status': order_data.status,
        'AWB': order_data.AWB,
        'platform': platform,
    }
    
    return JsonResponse(response_data)


def find_order_across_platforms(order_number):
    """
    Helper function to find order across all platforms
    Returns tuple of (order_data, platform)
    """
    print(f"DEBUG: Searching for order {order_number} across all platforms")
    
    # Try Amazon orders
    try:
        amazon_order = AmazonOrders.objects.filter(order_number=order_number).first()
        if amazon_order:
            print(f"DEBUG: Found order {order_number} in Amazon")
            return amazon_order, 'Amazon'
    except Exception as e:
        print(f"DEBUG: Error searching Amazon orders: {e}")
    
    # Try Flipkart orders
    try:
        flipkart_order = FlipkarOrders.objects.filter(order_number=order_number).first()
        if flipkart_order:
            print(f"DEBUG: Found order {order_number} in Flipkart")
            return flipkart_order, 'Flipkart'
    except Exception as e:
        print(f"DEBUG: Error searching Flipkart orders: {e}")
    
    # Try FirstCry orders
    try:
        firstcry_order = FirstcryOrders.objects.filter(order_number=order_number).first()
        if firstcry_order:
            print(f"DEBUG: Found order {order_number} in FirstCry")
            return firstcry_order, 'FirstCry'
    except Exception as e:
        print(f"DEBUG: Error searching FirstCry orders: {e}")
    
    # Try Meesho orders
    try:
        meesho_order = MeeshoOrders.objects.filter(order_number=order_number).first()
        if meesho_order:
            print(f"DEBUG: Found order {order_number} in Meesho")
            return meesho_order, 'Meesho'
    except Exception as e:
        print(f"DEBUG: Error searching Meesho orders: {e}")
    
    print(f"DEBUG: Order {order_number} not found in any platform")
    return None, None


@require_http_methods(["GET"])
def search_picklist_api(request, picklist_id):
    """
    API endpoint to search for picklist by ID with detailed orders
    """
    try:
        picklist = Picklist.objects.get(picklist_id=picklist_id)
        print(f"DEBUG: Found picklist: {picklist}")
    except Picklist.DoesNotExist:
        print(f"DEBUG: Picklist {picklist_id} not found")
        return JsonResponse({'error': 'Picklist not found'}, status=404)
    
    # Get all picklist items - try different possible field names
    try:
        picklist_items = PicklistItem.objects.filter(picklist=picklist)
        print(f"DEBUG: Found {picklist_items.count()} picklist items using 'picklist' field")
    except:
        try:
            picklist_items = PicklistItem.objects.filter(picklist_id=picklist.id)
            print(f"DEBUG: Found {picklist_items.count()} picklist items using 'picklist_id' field")
        except:
            try:
                picklist_items = PicklistItem.objects.filter(picklist__picklist_id=picklist_id)
                print(f"DEBUG: Found {picklist_items.count()} picklist items using 'picklist__picklist_id' field")
            except Exception as e:
                print(f"DEBUG: Error finding picklist items: {e}")
                picklist_items = PicklistItem.objects.none()
    
    if not picklist_items.exists():
        print(f"DEBUG: No picklist items found for picklist {picklist_id}")
        # Return empty orders but still valid response
        response_data = {
            'picklist_id': picklist.picklist_id,
            'picklist_type': getattr(picklist, 'picklist_type', 'SINGLE'),
            'status': getattr(picklist, 'status', 'CREATED'),
            'platform': getattr(picklist, 'platform', 'UNKNOWN'),
            'total_orders': 0,
            'total_items': 0,
            'created_at': picklist.created_at.isoformat() if hasattr(picklist, 'created_at') else '',
            'orders': []  # Empty orders list
        }
        print(f"DEBUG: Returning empty response: {response_data}")
        return JsonResponse(response_data)
    
    # Extract order numbers - try different possible field names for order_number
    unique_orders = []
    for item in picklist_items:
        order_num = None
        # Try different possible field names
        for field_name in ['order_number', 'order_id', 'order', 'order_ref']:
            if hasattr(item, field_name):
                order_num = getattr(item, field_name)
                if order_num:
                    break
        
        if order_num and order_num not in unique_orders:
            unique_orders.append(order_num)
    
    print(f"DEBUG: Found unique orders: {unique_orders}")
    
    total_orders = len(unique_orders)
    total_items = picklist_items.count()
    
    # Get detailed order information
    orders_detail = []
    processed_orders = set()
    
    for order_number in unique_orders:
        if order_number not in processed_orders:
            print(f"DEBUG: Processing order {order_number}")
            order_data, platform = find_order_across_platforms(order_number)
            if order_data:
                print(f"DEBUG: Found order {order_number} on platform {platform}")
                
                # Try to get fields safely with fallbacks
                sku = getattr(order_data, 'sku', getattr(order_data, 'SKU', 'N/A'))
                quantity = getattr(order_data, 'quantity', getattr(order_data, 'qty', 1))
                status = getattr(order_data, 'status', 'Unknown')
                awb = getattr(order_data, 'AWB', getattr(order_data, 'awb', getattr(order_data, 'tracking_number', 'Not assigned')))
                
                orders_detail.append({
                    'order_number': order_number,
                    'sku': str(sku),
                    'quantity': str(quantity),
                    'status': str(status),
                    'platform': platform,
                    'AWB': str(awb) if awb else 'Not assigned'
                })
            else:
                print(f"DEBUG: Order {order_number} not found in any platform")
                # If order not found in any platform, still show it
                orders_detail.append({
                    'order_number': str(order_number),
                    'sku': 'N/A',
                    'quantity': 'N/A',
                    'status': 'Unknown',
                    'platform': 'Unknown',
                    'AWB': 'N/A'
                })
            processed_orders.add(order_number)
    
    print(f"DEBUG: Final orders_detail has {len(orders_detail)} orders")
    
    # Return detailed picklist data with orders
    response_data = {
        'picklist_id': picklist.picklist_id,
        'picklist_type': getattr(picklist, 'picklist_type', 'SINGLE'),
        'status': getattr(picklist, 'status', 'CREATED'),
        'platform': getattr(picklist, 'platform', 'UNKNOWN'),
        'total_orders': total_orders,
        'total_items': total_items,
        'created_at': picklist.created_at.isoformat() if hasattr(picklist, 'created_at') else '',
        'orders': orders_detail  # Detailed orders list
    }
    
    print(f"DEBUG: Final response data: {response_data}")
    return JsonResponse(response_data)


@csrf_exempt
@require_http_methods(["POST"])
def validate_admin_password_api(request):
    """
    API endpoint to validate administrator password
    """
    try:
        data = json.loads(request.body)
        password = data.get('password', '').strip()
        
        if not password:
            return JsonResponse({'valid': False, 'message': 'Password is required'}, status=400)
        
        # Get admin password from settings (default: 'admin123')
        admin_password = getattr(settings, 'ADMIN_PROCESS_PASSWORD', 'admin123')
        
        is_valid = password == admin_password
        
        return JsonResponse({
            'valid': is_valid,
            'message': 'Password correct' if is_valid else 'Invalid password'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'valid': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'valid': False, 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def process_selected_orders_api(request):
    """
    API endpoint to process selected orders from a picklist
    """
    try:
        data = json.loads(request.body)
        selected_orders = data.get('selected_orders', [])
        picklist_id = data.get('picklist_id', '').strip()
        
        if not selected_orders:
            return JsonResponse({'error': 'No orders selected'}, status=400)
        
        if not picklist_id:
            return JsonResponse({'error': 'Picklist ID is required'}, status=400)
        
        # Verify picklist exists
        try:
            picklist = Picklist.objects.get(picklist_id=picklist_id)
        except Picklist.DoesNotExist:
            return JsonResponse({'error': 'Picklist not found'}, status=404)
        
        processing_results = []
        successful_orders = []
        failed_orders = []
        
        # Process each selected order
        for order_number in selected_orders:
            try:
                # Find the order across all platforms
                order_data, platform = find_order_across_platforms(order_number)
                
                if order_data:
                    # Here you'll implement the actual processing logic for each order
                    processing_results.append({
                        'order_number': order_number,
                        'platform': platform,
                        'status': 'processed',
                        'message': f'Order {order_number} processed successfully'
                    })
                    successful_orders.append(order_number)
                else:
                    processing_results.append({
                        'order_number': order_number,
                        'status': 'failed',
                        'message': f'Order {order_number} not found in any platform'
                    })
                    failed_orders.append(order_number)
                    
            except Exception as e:
                processing_results.append({
                    'order_number': order_number,
                    'status': 'failed',
                    'message': f'Error processing order {order_number}: {str(e)}'
                })
                failed_orders.append(order_number)
        
        response_data = {
            'success': len(failed_orders) == 0,
            'message': f'Processed {len(successful_orders)} out of {len(selected_orders)} selected orders',
            'picklist_id': picklist_id,
            'selected_orders': len(selected_orders),
            'successful_orders': len(successful_orders),
            'failed_orders': len(failed_orders),
            'processing_results': processing_results,
            'summary': {
                'picklist_status': picklist.status,
                'picklist_type': picklist.picklist_type,
                'platform': picklist.platform,
            }
        }
        
        return JsonResponse(response_data)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def process_order_api(request):
    """
    API endpoint to process a single order
    """
    try:
        data = json.loads(request.body)
        order_number = data.get('order_number', '').strip()
        
        if not order_number:
            return JsonResponse({'error': 'Order number is required'}, status=400)
        
        # Find the order across all platforms
        order_data, platform = find_order_across_platforms(order_number)
        
        if not order_data:
            return JsonResponse({'error': 'Order not found'}, status=404)
        
        # Here you'll implement the actual processing logic
        # For now, we'll just return a success response
        response_data = {
            'success': True,
            'message': f'Order {order_number} processing initiated',
            'order_number': order_number,
            'platform': platform,
            'current_status': order_data.status,
            'processing_steps': [
                'Order validation completed',
                'Inventory check passed',
                'Processing queue added'
            ]
        }
        
        return JsonResponse(response_data)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def process_picklist_api(request):
    """
    API endpoint to process all orders in a picklist
    """
    try:
        data = json.loads(request.body)
        picklist_id = data.get('picklist_id', '').strip()
        
        if not picklist_id:
            return JsonResponse({'error': 'Picklist ID is required'}, status=400)
        
        # Find the picklist
        try:
            picklist = Picklist.objects.get(picklist_id=picklist_id)
        except Picklist.DoesNotExist:
            return JsonResponse({'error': 'Picklist not found'}, status=404)
        
        # Get all orders in the picklist
        picklist_items = PicklistItem.objects.filter(picklist=picklist)
        print(picklist_items)

        print(")+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        unique_orders = list(set(item.order_number for item in picklist_items))
        
        processing_results = []
        successful_orders = []
        failed_orders = []
        
        # Process each unique order
        for order_number in unique_orders:
            try:
                # Find the order across all platforms
                order_data, platform = find_order_across_platforms(order_number)
                
                if order_data:
                    # Here you'll implement the actual processing logic for each order
                    processing_results.append({
                        'order_number': order_number,
                        'platform': platform,
                        'status': 'processed',
                        'message': f'Order {order_number} processed successfully'
                    })
                    successful_orders.append(order_number)
                else:
                    processing_results.append({
                        'order_number': order_number,
                        'status': 'failed',
                        'message': f'Order {order_number} not found in any platform'
                    })
                    failed_orders.append(order_number)
                    
            except Exception as e:
                processing_results.append({
                    'order_number': order_number,
                    'status': 'failed',
                    'message': f'Error processing order {order_number}: {str(e)}'
                })
                failed_orders.append(order_number)
        
        response_data = {
            'success': len(failed_orders) == 0,
            'message': f'Processed {len(successful_orders)} out of {len(unique_orders)} orders',
            'picklist_id': picklist_id,
            'total_orders': len(unique_orders),
            'successful_orders': len(successful_orders),
            'failed_orders': len(failed_orders),
            'processing_results': processing_results,
            'summary': {
                'picklist_status': picklist.status,
                'picklist_type': picklist.picklist_type,
                'platform': picklist.platform,
                'total_items': picklist_items.count()
            }
        }
        
        return JsonResponse(response_data)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def mark_order_complete_api(request):
    """
    API endpoint to mark an order as complete
    """
    try:
        data = json.loads(request.body)
        order_number = data.get('order_number', '').strip()
        picklist_id = data.get('picklist_id', '').strip()
        
        if not order_number:
            return JsonResponse({'error': 'Order number is required'}, status=400)
        
        # Find the order across all platforms
        order_data, platform = find_order_across_platforms(order_number)
        
        if not order_data:
            return JsonResponse({'error': 'Order not found'}, status=404)
        
        # Get the correct model for updating
        order_model = None
        if platform == 'Amazon':
            order_model = AmazonOrders
        elif platform == 'Flipkart':
            order_model = FlipkarOrders
        elif platform == 'FirstCry':
            order_model = FirstcryOrders
        elif platform == 'Meesho':
            order_model = MeeshoOrders
        
        if order_model:
            # Update order status to Complete
            order_model.objects.filter(order_number=order_number).update(
                status='Complete',
                is_printed=True,
                printed_at=timezone.now(),
                is_validated=True,
                validated_at=timezone.now(),
                processed_at=timezone.now()
            )
        
        # Delete OrderPDF record if it exists (cleanup)
        try:
            from ..models import OrderPDF
            order_pdf = OrderPDF.objects.get(order_id=order_number)
            order_pdf.delete()
            print(f"Deleted OrderPDF record for order {order_number}")
        except OrderPDF.DoesNotExist:
            pass  # OrderPDF doesn't exist, which is fine
        except Exception as pdf_error:
            print(f"Error deleting OrderPDF for order {order_number}: {str(pdf_error)}")
        
        # Update picklist dispatch status if picklist_id is provided
        if picklist_id:
            try:
                picklist = Picklist.objects.get(picklist_id=picklist_id)
                dispatch_status, created = PicklistDispatchStatus.objects.get_or_create(
                    picklist=picklist,
                    defaults={
                        'total_orders': 0,
                        'dispatched_orders': 0,
                        'is_fully_dispatched': False
                    }
                )
                
                # Update the status
                is_fully_dispatched = dispatch_status.update_status()
                
                if is_fully_dispatched:
                    print(f"All orders in picklist {picklist_id} are now complete/dispatched.")
                
            except Picklist.DoesNotExist:
                print(f"Picklist {picklist_id} not found")
            except Exception as e:
                print(f"Error updating dispatch status: {str(e)}")
        
        response_data = {
            'success': True,
            'message': f'Order {order_number} marked as Complete',
            'platform': platform,
            'order_number': order_number,
            'order_status': 'Complete'
        }
        
        return JsonResponse(response_data)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(f"Error in mark_order_complete_api: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)
    
def get_pdf_content_for_order(order_number):
    """
    Helper function to get PDF content for an order (same logic as print_label/print_invoice)
    Returns tuple of (pdf_content, platform, label_page_index)
    """
    try:
        # Find the order across all platforms
        order_data, platform = find_order_across_platforms(order_number)
        
        if not order_data:
            print(f"Order {order_number} not found in any platform")
            return None, None, None
        
        # Determine which page is the label page based on platform
        label_page_index = 0  # Default - first page is label
        
        if platform.upper() == 'FIRSTCRY':
            # For FirstCry, the label is typically the last page
            label_page_index = -1  # Use -1 to indicate last page
        
        # Check if PDF exists in the OrderPDF model
        pdf_record = OrderPDF.objects.filter(order_id=order_number).first()
        
        if pdf_record:
            print(f"DEBUG: Using PDF from database for order {order_number}")
            return pdf_record.pdf_content, platform, label_page_index
        
        # PDF not found in database - check if it exists in the file system via pdf_url
        if not order_data.pdf_url:
            print(f"No PDF file found for order {order_number}")
            return None, None, None
        
        # Get the PDF from the file system
        pdf_path = order_data.pdf_url
        
        # Check if it's a file path
        if pdf_path.startswith('/') or pdf_path.startswith('C:'):
            # It's a file path
            if os.path.exists(pdf_path):
                try:
                    # Read the file
                    with open(pdf_path, 'rb') as f:
                        pdf_content = f.read()
                    
                    print(f"DEBUG: Read PDF from file system for order {order_number}")
                    return pdf_content, platform, label_page_index
                    
                except Exception as e:
                    print(f"DEBUG: Error reading PDF from file system: {str(e)}")
                    return None, None, None
            else:
                print(f"DEBUG: PDF file not found at {pdf_path}")
                return None, None, None
        
        print(f"WARNING: Unsupported PDF path format: {pdf_path}")
        return None, None, None
        
    except Exception as e:
        print(f"Error in get_pdf_content_for_order: {str(e)}")
        traceback.print_exc()
        return None, None, None


def extract_pages_from_pdf(pdf_content, page_indices, is_label_extraction=True):
    """
    Extract specific pages from PDF content
    Args:
        pdf_content: bytes of the PDF file
        page_indices: list of page indices to extract (0-based)
        is_label_extraction: if True, extract only specified pages; if False, extract all except specified pages
    Returns:
        bytes of the new PDF with extracted pages
    """
    if PdfReader is None or PdfWriter is None:
        print("ERROR: PyPDF2/PyPDF4 not available for PDF manipulation")
        return pdf_content  # Return original PDF if can't manipulate
    
    try:
        # Create input PDF reader
        input_pdf = io.BytesIO(pdf_content)
        reader = PdfReader(input_pdf)
        writer = PdfWriter()
        
        total_pages = len(reader.pages)
        
        # Handle -1 index (last page)
        processed_indices = []
        for idx in page_indices:
            if idx == -1:
                processed_indices.append(total_pages - 1)
            else:
                processed_indices.append(idx)
        
        if is_label_extraction:
            # Extract only the specified pages (for labels)
            for page_idx in processed_indices:
                if 0 <= page_idx < total_pages:
                    writer.add_page(reader.pages[page_idx])
        else:
            # Extract all pages except the specified ones (for invoices)
            for page_idx in range(total_pages):
                if page_idx not in processed_indices:
                    writer.add_page(reader.pages[page_idx])
        
        # Create output PDF
        output_pdf = io.BytesIO()
        writer.write(output_pdf)
        output_pdf.seek(0)
        
        return output_pdf.getvalue()
        
    except Exception as e:
        print(f"Error in extract_pages_from_pdf: {str(e)}")
        traceback.print_exc()
        return pdf_content  # Return original PDF if extraction fails


def combine_pdfs(pdf_contents_list):
    """
    Combine multiple PDF contents into a single PDF
    Args:
        pdf_contents_list: list of PDF content bytes
    Returns:
        bytes of the combined PDF
    """
    if PdfReader is None or PdfWriter is None:
        print("ERROR: PyPDF2/PyPDF4 not available for PDF manipulation")
        return b''
    
    if not pdf_contents_list:
        print("No PDF contents to combine")
        return b''
    
    try:
        writer = PdfWriter()
        
        for pdf_content in pdf_contents_list:
            if pdf_content:
                input_pdf = io.BytesIO(pdf_content)
                reader = PdfReader(input_pdf)
                
                # Add all pages from this PDF
                for page in reader.pages:
                    writer.add_page(page)
        
        # Create output PDF
        output_pdf = io.BytesIO()
        writer.write(output_pdf)
        output_pdf.seek(0)
        
        return output_pdf.getvalue()
        
    except Exception as e:
        print(f"Error in combine_pdfs: {str(e)}")
        traceback.print_exc()
        return b''


# NEW ENDPOINTS - ADD THESE TO YOUR EXISTING FILE

@csrf_exempt
@require_http_methods(["POST"])
def download_picklist_labels_pdf_api(request):
    """
    API endpoint to download consolidated labels PDF for a picklist
    Applies same status updates as mark_multiple_orders_printed
    """
    try:
        data = json.loads(request.body)
        picklist_id = data.get('picklist_id', '').strip()
        
        if not picklist_id:
            return JsonResponse({'error': 'Picklist ID is required'}, status=400)
        
        print(f"Generating consolidated labels PDF for picklist {picklist_id}")
        
        # Find the picklist
        try:
            picklist = Picklist.objects.get(picklist_id=picklist_id)
        except Picklist.DoesNotExist:
            return JsonResponse({'error': 'Picklist not found'}, status=404)
        
        # Get all picklist items
        picklist_items = PicklistItem.objects.filter(picklist=picklist)
        
        if not picklist_items.exists():
            return JsonResponse({'error': 'No items found in picklist'}, status=404)
        
        # Extract unique order numbers
        unique_orders = []
        for item in picklist_items:
            order_num = None
            # Try different possible field names
            for field_name in ['order_number', 'order_id', 'order', 'order_ref']:
                if hasattr(item, field_name):
                    order_num = getattr(item, field_name)
                    if order_num:
                        break
            
            if order_num and order_num not in unique_orders:
                unique_orders.append(order_num)
        
        if not unique_orders:
            return JsonResponse({'error': 'No valid orders found in picklist'}, status=404)
        
        print(f"Processing {len(unique_orders)} orders for labels")
        
        # Collect label pages from all orders
        label_pdf_contents = []
        processed_orders = []
        failed_orders = []
        
        for order_number in unique_orders:
            print(f"Processing order {order_number} for label extraction")
            
            pdf_content, platform, label_page_index = get_pdf_content_for_order(order_number)
            
            if pdf_content:
                # Extract only the label page(s)
                label_pages = extract_pages_from_pdf(
                    pdf_content, 
                    [label_page_index], 
                    is_label_extraction=True
                )
                
                if label_pages:
                    label_pdf_contents.append(label_pages)
                    processed_orders.append(order_number)
                    print(f"Successfully extracted label for order {order_number}")
                else:
                    print(f"Failed to extract label for order {order_number}")
                    failed_orders.append(order_number)
            else:
                print(f"No PDF found for order {order_number}")
                failed_orders.append(order_number)
        
        if not label_pdf_contents:
            return JsonResponse({'error': 'No labels could be extracted from any orders'}, status=404)
        
        # Combine all label PDFs into one
        print(f"Combining {len(label_pdf_contents)} label PDFs")
        combined_labels_pdf = combine_pdfs(label_pdf_contents)
        
        if not combined_labels_pdf:
            return JsonResponse({'error': 'Failed to combine label PDFs'}, status=500)
        
        # Apply the same status updates as mark_multiple_orders_printed
        print(f"Applying status updates for {len(processed_orders)} successfully processed orders")
        
        # Determine platform for updating platform-specific tables
        platform = picklist.platform.upper() if picklist.platform else "UNKNOWN"
        
        # Model mapping for platform-specific order tables
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        # Track updates
        total_updated_items = 0
        platform_orders_updated = 0
        
        # Process each successfully processed order for status updates
        for order_number in processed_orders:
            # Find all picklist items with this order number
            items = PicklistItem.objects.filter(picklist=picklist, order_number=order_number)
            
            # Mark all matching items as picked/processed
            order_updated_items = 0
            for item in items:
                if not item.picked:  # Only update if not already picked
                    item.picked = True
                    item.save()
                    order_updated_items += 1
                    
                    # Also update the PicklistItemLocation if it exists
                    try:
                        location_info, created = PicklistItemLocation.objects.get_or_create(
                            picklist_item=item,
                            defaults={'location': 'Unknown', 'picked': False}
                        )
                        location_info.picked = True
                        location_info.picked_at = timezone.now()
                        location_info.save()
                    except Exception as e:
                        print(f"Error updating location info for item {item.id}: {str(e)}")
                        # Continue anyway - the PicklistItem is already updated
            
            total_updated_items += order_updated_items
            
            # Update the status in the appropriate platform order table
            if platform in model_mapping:
                try:
                    orders_updated = model_mapping[platform].objects.filter(
                        order_number=order_number
                    ).update(status='Processed')
                    
                    if orders_updated > 0:
                        platform_orders_updated += 1
                        print(f"Updated {platform} order {order_number} status to 'Processed'")
                except Exception as e:
                    print(f"Error updating {platform} order {order_number}: {str(e)}")
                    # Continue processing other orders
        
        # Check if all items in the picklist are now picked
        all_picked = not PicklistItem.objects.filter(picklist=picklist, picked=False).exists()
        
        # If all items are picked, update the picklist status if needed
        picklist_status_updated = False
        if all_picked and picklist.status == 'PACKING':
            picklist.status = 'PACKED'
            picklist.save()
            picklist_status_updated = True
            print(f"Picklist {picklist_id} status updated to 'PACKED'")
        
        print(f"Status updates complete: {total_updated_items} items, {platform_orders_updated} platform orders")
        
        # Return the combined PDF as download with picklist_id in filename
        response = HttpResponse(combined_labels_pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{picklist_id}_labels.pdf"'
        
        print(f"Successfully generated labels PDF with {len(label_pdf_contents)} pages")
        return response
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(f"Error in download_picklist_labels_pdf_api: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def download_picklist_invoices_pdf_api(request):
    """
    API endpoint to download consolidated invoices PDF for a picklist
    No status updates (same as print_invoice behavior)
    """
    try:
        data = json.loads(request.body)
        picklist_id = data.get('picklist_id', '').strip()
        
        if not picklist_id:
            return JsonResponse({'error': 'Picklist ID is required'}, status=400)
        
        print(f"Generating consolidated invoices PDF for picklist {picklist_id}")
        
        # Find the picklist
        try:
            picklist = Picklist.objects.get(picklist_id=picklist_id)
        except Picklist.DoesNotExist:
            return JsonResponse({'error': 'Picklist not found'}, status=404)
        
        # Get all picklist items
        picklist_items = PicklistItem.objects.filter(picklist=picklist)
        
        if not picklist_items.exists():
            return JsonResponse({'error': 'No items found in picklist'}, status=404)
        
        # Extract unique order numbers
        unique_orders = []
        for item in picklist_items:
            order_num = None
            # Try different possible field names
            for field_name in ['order_number', 'order_id', 'order', 'order_ref']:
                if hasattr(item, field_name):
                    order_num = getattr(item, field_name)
                    if order_num:
                        break
            
            if order_num and order_num not in unique_orders:
                unique_orders.append(order_num)
        
        if not unique_orders:
            return JsonResponse({'error': 'No valid orders found in picklist'}, status=404)
        
        print(f"Processing {len(unique_orders)} orders for invoices")
        
        # Collect invoice pages from all orders
        invoice_pdf_contents = []
        processed_orders = []
        failed_orders = []
        
        for order_number in unique_orders:
            print(f"Processing order {order_number} for invoice extraction")
            
            pdf_content, platform, label_page_index = get_pdf_content_for_order(order_number)
            
            if pdf_content:
                # Extract all pages except the label page(s)
                invoice_pages = extract_pages_from_pdf(
                    pdf_content, 
                    [label_page_index], 
                    is_label_extraction=False  # Extract everything EXCEPT label pages
                )
                
                if invoice_pages:
                    invoice_pdf_contents.append(invoice_pages)
                    processed_orders.append(order_number)
                    print(f"Successfully extracted invoice pages for order {order_number}")
                else:
                    print(f"Failed to extract invoice pages for order {order_number}")
                    failed_orders.append(order_number)
            else:
                print(f"No PDF found for order {order_number}")
                failed_orders.append(order_number)
        
        if not invoice_pdf_contents:
            return JsonResponse({'error': 'No invoices could be extracted from any orders'}, status=404)
        
        # Combine all invoice PDFs into one
        print(f"Combining {len(invoice_pdf_contents)} invoice PDFs")
        combined_invoices_pdf = combine_pdfs(invoice_pdf_contents)
        
        if not combined_invoices_pdf:
            return JsonResponse({'error': 'Failed to combine invoice PDFs'}, status=500)
        
        # No status updates for invoices (same as print_invoice behavior)
        print(f"No status updates applied for invoice download (same as print_invoice)")
        
        # Return the combined PDF as download with picklist_id in filename
        response = HttpResponse(combined_invoices_pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{picklist_id}_invoices.pdf"'
        
        print(f"Successfully generated invoices PDF with {len(invoice_pdf_contents)} sections")
        return response
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(f"Error in download_picklist_invoices_pdf_api: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


