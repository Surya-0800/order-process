# Updated API endpoints for the Dispatch Dashboard

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.db.models import Count, Case, When, IntegerField, F, Q
from django.utils import timezone
import json,os
import traceback
from django.views.decorators.http import require_POST
from ordercycle.models import Picklist, PicklistItem, AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders,PicklistDispatchStatus
from django.views.decorators.csrf import csrf_exempt



# Get picklists with orders in Complete status (changed from Dispatch)
def get_dispatch_picklists(request):
    """
    Get picklists with orders in Complete status
    """
    try:
        # Try to get PicklistDispatchStatus records first
        picklists_data = []
        using_dispatch_model = False
        
        try:
            # Check if PicklistDispatchStatus model is available
            from django.apps import apps
            PicklistDispatchStatus = apps.get_model('ordercycle', 'PicklistDispatchStatus')
            
            # Query using the PicklistDispatchStatus model
            dispatch_statuses = PicklistDispatchStatus.objects.select_related('picklist').all()
            
            if dispatch_statuses.exists():
                using_dispatch_model = True
                print(f"Found {dispatch_statuses.count()} dispatch status records")
                
                # Include picklists with at least one completed order
                for status in dispatch_statuses:
                    if status.dispatched_orders > 0:
                        percentage = 0
                        if status.total_orders > 0:
                            percentage = (status.dispatched_orders / status.total_orders) * 100
                        
                        picklist = status.picklist
                        picklists_data.append({
                            'picklist_id': picklist.picklist_id,
                            'picklist_type': picklist.picklist_type,
                            'platform': picklist.platform,
                            'total_orders': status.total_orders,
                            'dispatch_orders': status.dispatched_orders,
                            'dispatch_percentage': round(percentage, 1),
                            'status': picklist.status,
                            'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S')
                        })
                
                print(f"Using dispatch model, found {len(picklists_data)} picklists with complete orders")
        except Exception as e:
            print(f"Error using PicklistDispatchStatus model: {str(e)}")
            using_dispatch_model = False
        
        # If no dispatch model or no records found, fall back to original implementation
        if not using_dispatch_model or not picklists_data:
            print("Falling back to original implementation")
            
            # Get all picklists
            picklists = Picklist.objects.all()
            print(f"Found {picklists.count()} picklists")
            
            for picklist in picklists:
                picklist_items = PicklistItem.objects.filter(picklist=picklist)
                total_orders = picklist_items.values('order_number').distinct().count()
                
                if total_orders == 0:
                    continue  # Skip picklists with no orders
                
                # Count orders in Complete status for this picklist
                dispatch_orders = 0
                platform = picklist.platform.upper()
                order_numbers = picklist_items.values_list('order_number', flat=True).distinct()
                
                for order_number in order_numbers:
                    dispatch_found = False
                    
                    if platform == 'AMAZON':
                        dispatch_found = AmazonOrders.objects.filter(order_number=order_number, status='Complete').exists()
                    elif platform == 'FLIPKART':
                        dispatch_found = FlipkarOrders.objects.filter(order_number=order_number, status='Complete').exists()
                    elif platform == 'FIRSTCRY':
                        dispatch_found = FirstcryOrders.objects.filter(order_number=order_number, status='Complete').exists()
                    elif platform == 'MEESHO':
                        dispatch_found = MeeshoOrders.objects.filter(order_number=order_number, status='Complete').exists()
                    
                    if dispatch_found:
                        dispatch_orders += 1
                
                # Only include picklists that have at least one order in Complete status
                if dispatch_orders > 0:
                    dispatch_percentage = 0
                    if total_orders > 0:
                        dispatch_percentage = (dispatch_orders / total_orders) * 100
                    
                    picklists_data.append({
                        'picklist_id': picklist.picklist_id,
                        'picklist_type': picklist.picklist_type,
                        'platform': picklist.platform,
                        'total_orders': total_orders,
                        'dispatch_orders': dispatch_orders,
                        'dispatch_percentage': round(dispatch_percentage, 1),
                        'status': picklist.status,
                        'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S')
                    })
        
        # Sort by dispatch percentage (descending)
        picklists_data.sort(key=lambda x: x['dispatch_percentage'], reverse=True)
        
        print(f"Returning {len(picklists_data)} picklists with complete orders")
        
        return JsonResponse({
            'status': 'success',
            'picklists': picklists_data,
            'using_dispatch_model': using_dispatch_model
        })
    
    except Exception as e:
        print(f"Error in get_dispatch_picklists: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return JsonResponse({
            'status': 'error',
            'message': f'Error retrieving dispatch picklists: {str(e)}',
            'picklists': []
        })  

# Get dispatch orders for a specific picklist
def get_dispatch_orders(request, picklist_id):
    """
    Get completed orders for a specific picklist, making sure completed orders are returned first
    """
    try:
        picklist = get_object_or_404(Picklist, picklist_id=picklist_id)
        picklist_items = PicklistItem.objects.filter(picklist=picklist)
        
        total_orders = picklist_items.values('order_number').distinct().count()
        dispatch_orders = 0
        orders_data = []
        
        platform = picklist.platform.upper()
        order_numbers = picklist_items.values_list('order_number', flat=True).distinct()
        
        for order_number in order_numbers:
            # Get the order based on platform
            if platform == 'AMAZON':
                orders = AmazonOrders.objects.filter(order_number=order_number)
            elif platform == 'FLIPKART':
                orders = FlipkarOrders.objects.filter(order_number=order_number)
            elif platform == 'FIRSTCRY':
                orders = FirstcryOrders.objects.filter(order_number=order_number)
            elif platform == 'MEESHO':
                orders = MeeshoOrders.objects.filter(order_number=order_number)
            else:
                continue
            
            if not orders.exists():
                continue
            
            order = orders.first()
            
            # Count completed orders
            is_dispatch = order.status == 'Complete'
            if is_dispatch:
                dispatch_orders += 1
            
            # Find the associated picklist items
            items = picklist_items.filter(order_number=order_number)
            
            # Add each item as a separate entry in orders_data
            for item in items:
                orders_data.append({
                    'order_number': order.order_number,
                    'sku': item.sku,
                    'quantity': item.quantity,
                    'status': order.status,
                    'awb': order.AWB if hasattr(order, 'AWB') else None,
                    'is_dispatch': is_dispatch  # Add this flag to help with sorting
                })
        
        # Sort orders - Complete first, then others
        orders_data.sort(key=lambda x: (not x['is_dispatch']))
        
        # Remove the temporary sorting flag
        for order in orders_data:
            order.pop('is_dispatch', None)
        
        # Calculate dispatch percentage
        dispatch_percentage = 0
        if total_orders > 0:
            dispatch_percentage = round((dispatch_orders / total_orders) * 100)
        
        response_data = {
            'picklist_id': picklist.picklist_id,
            'platform': picklist.platform,
            'total_orders': total_orders,
            'dispatch_orders': dispatch_orders,
            'dispatch_percentage': dispatch_percentage,
            'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'orders': orders_data
        }
        
        return JsonResponse(response_data)
    
    except Exception as e:
        print(f"Error in get_dispatch_orders: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return JsonResponse({
            'status': 'error',
            'message': f'Error retrieving dispatch orders: {str(e)}'
        }, status=500)

# Mark orders as dispatched (now completed)
def mark_orders_as_dispatched(request, picklist_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    picklist = get_object_or_404(Picklist, picklist_id=picklist_id)
    platform = picklist.platform.upper()
    
    try:
        data = json.loads(request.body)
        order_numbers = data.get('order_numbers', [])
        
        if not order_numbers:
            return JsonResponse({'error': 'No orders provided'}, status=400)
        
        # Update order status based on platform
        updated_count = 0
        
        for order_number in order_numbers:
            if platform == 'AMAZON':
                orders = AmazonOrders.objects.filter(order_number=order_number)
            elif platform == 'FLIPKART':
                orders = FlipkarOrders.objects.filter(order_number=order_number)
            elif platform == 'FIRSTCRY':
                orders = FirstcryOrders.objects.filter(order_number=order_number)
            elif platform == 'MEESHO':
                orders = MeeshoOrders.objects.filter(order_number=order_number)
            else:
                continue
            
            if orders.exists():
                orders.update(status='Complete')  # Changed from 'Dispatch' to 'Complete'
                updated_count += 1
        
        # Check if all orders in picklist are now completed
        # Use the PicklistDispatchStatus model if available
        try:
            dispatch_status, created = PicklistDispatchStatus.objects.get_or_create(
                picklist=picklist,
                defaults={
                    'total_orders': 0,
                    'dispatched_orders': 0,
                    'is_fully_dispatched': False
                }
            )
            
            # Update the status
            all_dispatched = dispatch_status.update_status()
            
            # Include dispatch status info in the response
            dispatch_info = {
                'total_orders': dispatch_status.total_orders,
                'dispatched_orders': dispatch_status.dispatched_orders,
                'percentage': round((dispatch_status.dispatched_orders / dispatch_status.total_orders * 100), 1) if dispatch_status.total_orders > 0 else 0,
                'is_fully_dispatched': dispatch_status.is_fully_dispatched
            }
            
        except Exception as e:
            print(f"Error updating dispatch status: {str(e)}")
            # Fall back to the old implementation
            all_dispatched = check_all_dispatched(picklist, platform)
            dispatch_info = None
        
        response_data = {
            'success': True,
            'message': f'Successfully marked {updated_count} order(s) as completed.',  # Changed wording
            'all_dispatched': all_dispatched
        }
        
        if dispatch_info:
            response_data['dispatch_info'] = dispatch_info
        
        return JsonResponse(response_data)
    
    except Exception as e:
        print(f"Error in mark_orders_as_dispatched: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
    
# Helper function to check if all orders in a picklist are dispatched (now completed)
def check_all_dispatched(picklist, platform):
    """
    Check if all orders in a picklist are completed and update the PicklistDispatchStatus
    """
    try:
        # Get or create dispatch status for this picklist
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
        
        return is_fully_dispatched
    except Exception as e:
        print(f"Error in check_all_dispatched: {str(e)}")
        traceback.print_exc()
        
        # Fall back to the old implementation
        picklist_items = PicklistItem.objects.filter(picklist=picklist)
        all_dispatched = True
        
        for item in picklist_items:
            order_number = item.order_number
            
            if platform == 'AMAZON':
                order = AmazonOrders.objects.filter(order_number=order_number).first()
            elif platform == 'FLIPKART':
                order = FlipkarOrders.objects.filter(order_number=order_number).first()
            elif platform == 'FIRSTCRY':
                order = FirstcryOrders.objects.filter(order_number=order_number).first()
            elif platform == 'MEESHO':
                order = MeeshoOrders.objects.filter(order_number=order_number).first()
            else:
                continue
            
            if not order or order.status != 'Complete':  # Changed from 'Dispatch' to 'Complete'
                all_dispatched = False
                break
        
        return all_dispatched

def search_by_awb(request):
    """
    Search orders by AWB number
    """
    try:
        awb = request.GET.get('awb')
        if not awb:
            return JsonResponse({'error': 'AWB number is required'}, status=400)
        
        # Find orders with this AWB across all platforms
        orders = []
        
        # Amazon orders
        amazon_orders = AmazonOrders.objects.filter(AWB=awb)
        for order in amazon_orders:
            orders.append({
                'id': order.id,
                'order_number': order.order_number,
                'platform': 'AMAZON',
                'sku': order.sku,
                'quantity': order.quantity,
                'status': order.status,
                'awb': order.AWB
            })
        
        # Flipkart orders
        flipkart_orders = FlipkarOrders.objects.filter(AWB=awb)
        for order in flipkart_orders:
            orders.append({
                'id': order.id,
                'order_number': order.order_number,
                'platform': 'FLIPKART',
                'sku': order.sku,
                'quantity': order.quantity,
                'status': order.status,
                'awb': order.AWB
            })
        
        # FirstCry orders
        firstcry_orders = FirstcryOrders.objects.filter(AWB=awb)
        for order in firstcry_orders:
            orders.append({
                'id': order.id,
                'order_number': order.order_number,
                'platform': 'FIRSTCRY',
                'sku': order.sku,
                'quantity': order.quantity,
                'status': order.status,
                'awb': order.AWB
            })
        
        # Meesho orders
        meesho_orders = MeeshoOrders.objects.filter(AWB=awb)
        for order in meesho_orders:
            orders.append({
                'id': order.id,
                'order_number': order.order_number,
                'platform': 'MEESHO',
                'sku': order.sku,
                'quantity': order.quantity,
                'status': order.status,
                'awb': order.AWB
            })
        
        return JsonResponse({
            'orders': orders
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
    
# API endpoints for changing order status from Complete to Dispatch

from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json
import traceback
from django.shortcuts import get_object_or_404
from ordercycle.models import AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders

@csrf_exempt
@require_POST
def change_to_dispatch(request):
    """
    Change an order status from Complete to Dispatch and delete PDF file if exists
    """
    try:
        data = json.loads(request.body)
        order_number = data.get('order_number')
        platform = data.get('platform')
        awb = data.get('awb')  # Optional, for validation
        
        if not order_number or not platform:
            return JsonResponse({
                'error': 'Order number and platform are required'
            }, status=400)
        
        # Select the appropriate model based on platform
        model = None
        if platform.upper() == 'AMAZON':
            model = AmazonOrders
        elif platform.upper() == 'FLIPKART':
            model = FlipkarOrders
        elif platform.upper() == 'FIRSTCRY':
            model = FirstcryOrders
        elif platform.upper() == 'MEESHO':
            model = MeeshoOrders
        else:
            return JsonResponse({
                'error': f'Unknown platform: {platform}'
            }, status=400)
        
        # Find the order
        orders = model.objects.filter(order_number=order_number)
        
        if not orders.exists():
            return JsonResponse({
                'error': f'Order {order_number} not found for platform {platform}'
            }, status=404)
        
        # Validate AWB if provided
        if awb:
            matching_orders = orders.filter(AWB=awb)
            if not matching_orders.exists():
                return JsonResponse({
                    'error': f'No order found with order number {order_number} and AWB {awb}'
                }, status=404)
            orders = matching_orders
        
        # Verify current status is Complete
        complete_orders = orders.filter(status='Complete')
        if not complete_orders.exists():
            return JsonResponse({
                'error': f'No orders with status "Complete" found for order number {order_number}'
            }, status=400)
        
        # Check for PDF files and delete them
        deleted_files = 0
        
        for order in complete_orders:
            pdf_path = getattr(order, 'pdf_path', None)
            if pdf_path and pdf_path.strip() and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                    deleted_files += 1
                    print(f"Deleted PDF file: {pdf_path}")
                except Exception as e:
                    print(f"Error deleting PDF file {pdf_path}: {str(e)}")
            
            # Optional: Clear the pdf_path field after deleting the file
            if hasattr(order, 'pdf_path'):
                order.pdf_path = ''
        
        # Update status to Dispatch
        updated_count = complete_orders.update(status='Dispatch')
        
        return JsonResponse({
            'message': f'Successfully changed {updated_count} order(s) from Complete to Dispatch status',
            'updated_count': updated_count,
            'deleted_files': deleted_files,
            'order_number': order_number
        })
    
    except Exception as e:
        print(f"Error in change_to_dispatch: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_POST
def bulk_change_to_dispatch(request):
    """
    Change multiple orders' status from Complete to Dispatch and delete PDF files
    """
    try:
        data = json.loads(request.body)
        orders = data.get('orders', [])
        awb = data.get('awb')  # Optional, for validation
        
        if not orders:
            return JsonResponse({
                'error': 'No orders provided'
            }, status=400)
        
        # Track updated orders and deleted files
        updated_count = 0
        deleted_files = 0
        failed_orders = []
        
        # Process each order
        for order_data in orders:
            order_number = order_data.get('order_number')
            platform = order_data.get('platform')
            
            if not order_number or not platform:
                failed_orders.append({
                    'order_number': order_number,
                    'platform': platform,
                    'reason': 'Missing order number or platform'
                })
                continue
            
            # Select the appropriate model based on platform
            model = None
            if platform.upper() == 'AMAZON':
                model = AmazonOrders
            elif platform.upper() == 'FLIPKART':
                model = FlipkarOrders
            elif platform.upper() == 'FIRSTCRY':
                model = FirstcryOrders
            elif platform.upper() == 'MEESHO':
                model = MeeshoOrders
            else:
                failed_orders.append({
                    'order_number': order_number,
                    'platform': platform,
                    'reason': f'Unknown platform: {platform}'
                })
                continue
            
            # Find the order
            query = model.objects.filter(order_number=order_number)
            
            # Add AWB filter if provided
            if awb:
                query = query.filter(AWB=awb)
            
            # Filter for Complete status
            complete_orders = query.filter(status='Complete')
            
            if not complete_orders.exists():
                failed_orders.append({
                    'order_number': order_number,
                    'platform': platform,
                    'reason': 'No matching Complete orders found'
                })
                continue
            
            # Check for PDF files and delete them
            for order in complete_orders:
                pdf_path = getattr(order, 'pdf_path', None)
                if pdf_path and pdf_path.strip() and os.path.exists(pdf_path):
                    try:
                        os.remove(pdf_path)
                        deleted_files += 1
                        print(f"Deleted PDF file: {pdf_path}")
                    except Exception as e:
                        print(f"Error deleting PDF file {pdf_path}: {str(e)}")
                
                # Optional: Clear the pdf_path field after deleting the file
                if hasattr(order, 'pdf_path'):
                    order.pdf_path = ''
                    order.save()
            
            # Update to Dispatch
            count = complete_orders.update(status='Dispatch')
            updated_count += count
        
        return JsonResponse({
            'message': f'Successfully changed {updated_count} order(s) from Complete to Dispatch status and deleted {deleted_files} PDF files',
            'updated_count': updated_count,
            'deleted_files': deleted_files,
            'failed_orders': failed_orders
        })
    
    except Exception as e:
        print(f"Error in bulk_change_to_dispatch: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'error': str(e)
        }, status=500)
    

# Also update the complete-by-awb endpoint to exempt CSRF
@csrf_exempt
@require_POST
def complete_orders_by_awb(request):
    """
    Find orders by AWB number and change their status from Dispatch to Complete
    """
    try:
        data = json.loads(request.body)
        awb = data.get('awb')
        
        if not awb:
            return JsonResponse({'error': 'AWB number is required'}, status=400)
        
        # Count of updated orders for each platform
        updated_count = {
            'AMAZON': 0,
            'FLIPKART': 0,
            'FIRSTCRY': 0,
            'MEESHO': 0
        }
        
        # Update Amazon orders
        amazon_orders = AmazonOrders.objects.filter(AWB=awb, status='Dispatch')
        if amazon_orders.exists():
            updated_count['AMAZON'] = amazon_orders.count()
            amazon_orders.update(status='Complete')
        
        # Update Flipkart orders
        flipkart_orders = FlipkarOrders.objects.filter(AWB=awb, status='Dispatch')
        if flipkart_orders.exists():
            updated_count['FLIPKART'] = flipkart_orders.count()
            flipkart_orders.update(status='Complete')
        
        # Update FirstCry orders
        firstcry_orders = FirstcryOrders.objects.filter(AWB=awb, status='Dispatch')
        if firstcry_orders.exists():
            updated_count['FIRSTCRY'] = firstcry_orders.count()
            firstcry_orders.update(status='Complete')
        
        # Update Meesho orders
        meesho_orders = MeeshoOrders.objects.filter(AWB=awb, status='Dispatch')
        if meesho_orders.exists():
            updated_count['MEESHO'] = meesho_orders.count()
            meesho_orders.update(status='Complete')
        
        total_updated = sum(updated_count.values())
        
        if total_updated == 0:
            return JsonResponse({
                'message': f'No orders in Dispatch status found with AWB: {awb}',
                'updated': False,
                'counts': updated_count
            })
        
        platforms_updated = [p for p, c in updated_count.items() if c > 0]
        platforms_text = ', '.join(platforms_updated)
        
        return JsonResponse({
            'message': f'Successfully updated {total_updated} orders from Dispatch to Complete (Platforms: {platforms_text})',
            'updated': True,
            'counts': updated_count
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@require_POST
def complete_orders_by_awb(request):
    """
    Find orders by AWB number and change their status from Dispatch to Complete
    """
    try:
        data = json.loads(request.body)
        awb = data.get('awb')
        
        if not awb:
            return JsonResponse({'error': 'AWB number is required'}, status=400)
        
        # Count of updated orders for each platform
        updated_count = {
            'AMAZON': 0,
            'FLIPKART': 0,
            'FIRSTCRY': 0,
            'MEESHO': 0
        }
        
        # Update Amazon orders - now finding 'Dispatch' status to update to 'Complete'
        amazon_orders = AmazonOrders.objects.filter(AWB=awb, status='Dispatch')
        if amazon_orders.exists():
            updated_count['AMAZON'] = amazon_orders.count()
            amazon_orders.update(status='Complete')
        
        # Update Flipkart orders
        flipkart_orders = FlipkarOrders.objects.filter(AWB=awb, status='Dispatch')
        if flipkart_orders.exists():
            updated_count['FLIPKART'] = flipkart_orders.count()
            flipkart_orders.update(status='Complete')
        
        # Update FirstCry orders
        firstcry_orders = FirstcryOrders.objects.filter(AWB=awb, status='Dispatch')
        if firstcry_orders.exists():
            updated_count['FIRSTCRY'] = firstcry_orders.count()
            firstcry_orders.update(status='Complete')
        
        # Update Meesho orders
        meesho_orders = MeeshoOrders.objects.filter(AWB=awb, status='Dispatch')
        if meesho_orders.exists():
            updated_count['MEESHO'] = meesho_orders.count()
            meesho_orders.update(status='Complete')
        
        total_updated = sum(updated_count.values())
        
        if total_updated == 0:
            return JsonResponse({
                'message': f'No orders in Dispatch status found with AWB: {awb}',
                'updated': False,
                'counts': updated_count
            })
        
        platforms_updated = [p for p, c in updated_count.items() if c > 0]
        platforms_text = ', '.join(platforms_updated)
        
        return JsonResponse({
            'message': f'Successfully updated {total_updated} orders from Dispatch to Complete (Platforms: {platforms_text})',
            'updated': True,
            'counts': updated_count
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)