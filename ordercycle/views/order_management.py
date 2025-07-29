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
    Picklist, PicklistItem, MasterTable, PicklistDispatchStatus
)


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