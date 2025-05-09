"""
Views for handling packing stage functionality.
"""
import os
import json
import traceback
from django.utils import timezone
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.contrib.sites.shortcuts import get_current_site
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from ..models import (
    Picklist, PicklistItem, PicklistItemLocation, MasterTable,
    AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders,
    UserProfile,PicklistDispatchStatus
)


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
        # Get picklist with PACKING status
        picklist = Picklist.objects.get(picklist_id=picklist_id, status='PACKING')
        
        # Get picklist items with their details
        items = PicklistItem.objects.filter(picklist=picklist).select_related('location_info')
        
        items_data = []
        for item in items:
            # Get location info if available
            location = "Unknown"
            
            # Use the actual picked status from the database
            picked = item.picked
            
            picker_id = None
            
            if hasattr(item, 'location_info'):
                location = item.location_info.location
                picker_id = item.location_info.picker.picker_id if item.location_info.picker else None
            
            # Check order status across platforms to exclude Dispatch orders
            order_number = item.order_number
            order_status = None
            awb = None
            
            # Find the order and its status across all platforms
            for model in [AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders]:
                order = model.objects.filter(order_number=order_number).first()
                if order:
                    order_status = order.status
                    awb = order.AWB
                    break
            
            # CRITICAL: Only include orders that are NOT in Dispatch status
            if order_status != 'Dispatch':
                items_data.append({
                    'id': item.id,
                    'order_number': item.order_number,
                    'sku': item.sku,
                    'quantity': item.quantity,
                    'location': location,
                    'picked': picked,
                    'picker_id': picker_id,
                    'awb': awb,
                    'order_status': order_status  # Include status for debugging
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
        # Construct the image path based on product ID
        image_path = f"/media/ASINWISEIMAGES/{product_id}.jpg"
        
        # Check if the file exists
        import os
        from django.conf import settings
        
        full_image_path = os.path.join(settings.MEDIA_ROOT, "ASINWISEIMAGES", f"{product_id}.jpg")
        if not os.path.exists(full_image_path):
            # If image doesn't exist, use a default "not found" image
            image_path = "/static/images/no_image_found.jpg"
        
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
def get_picklist_barcode(request, picklist_id):
    """
    API endpoint to generate barcode data for a picklist
    This could be used as an alternative to client-side barcode generation
    """
    try:
        # Check if picklist exists
        picklist = Picklist.objects.get(picklist_id=picklist_id)
        
        # Return barcode data
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


@require_http_methods(["GET"])
def get_product_image_by_sku(request):
    """API endpoint to get product image URL and other details by SKU"""
    sku = request.GET.get('sku')
    
    if not sku:
        return JsonResponse({'error': 'SKU parameter is required'}, status=400)
    
    try:
        # Query the database for a product with this SKU
        product = MasterTable.objects.filter(sku=sku).first()
        
        if not product:
            # If no product is found, return default values
            return JsonResponse({
                'sku': sku,
                'image_url': f"ASINWISEIMAGES/{sku}.jpg",
                'product_name': f"Product (SKU: {sku})",
                'product_id': '',
                'location': 'Unknown',
                'box_no': '',
                'mrp': None,
                'generic_name': f"Product (SKU: {sku})",
                'pack_check': '',
                'pack_remarks': ''
            })
        
        # Return all the requested fields
        return JsonResponse({
            'sku': product.sku,
            'image_url': product.image_url,
            'product_id': product.product_id or '',
            'location': product.location or 'Unknown',
            'box_no': product.box_no or '',
            'mrp': float(product.mrp) if product.mrp is not None else None,
            'generic_name': product.generic_name or f"Product (SKU: {sku})",
            'pack_check': product.pack_check or '',
            'pack_remarks': product.pack_remarks or ''
        })
        
    except Exception as e:
        print(f"Error retrieving product data: {str(e)}")
        return JsonResponse({'error': f'Error retrieving product data: {str(e)}'}, status=500)
   
@require_http_methods(["POST"])
def save_awb_and_dispatch(request):
    """
    Save the AWB number for an order and move it to Dispatch status.
    Also updates the PicklistDispatchStatus for tracking dispatch progress.
    """
    try:
        data = json.loads(request.body)
        order_number = data.get('order_number')
        awb = data.get('awb')
        picklist_id = data.get('picklist_id')  # Get picklist_id from request
        
        if not order_number or not awb:
            return JsonResponse({
                'status': 'error',
                'message': 'Order number and AWB are required'
            }, status=400)
        
        # Find the platform for this order
        platform = None
        updated = 0
        
        # Try each platform table to find the order
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        for plat, model in model_mapping.items():
            if model.objects.filter(order_number=order_number).exists():
                platform = plat
                # Update order with AWB and new status
                result = model.objects.filter(order_number=order_number).update(
                    AWB=awb,
                    status='Dispatch'  # Ensure this status is exactly 'Dispatch'
                )
                updated = result
                
                # Verify the update was successful by retrieving the order
                updated_order = model.objects.filter(order_number=order_number).first()
                if updated_order:
                    print(f"Order {order_number} updated. Status: {updated_order.status}")
                
                break
                
        if not platform:
            return JsonResponse({
                'status': 'error',
                'message': f'Order {order_number} not found in any platform'
            }, status=404)
        
        # Update dispatch status if picklist_id is provided
        dispatch_status = None
        if picklist_id:
            try:
                # Find the picklist
                picklist = Picklist.objects.get(picklist_id=picklist_id)
                
                # Get or create dispatch status record
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
                    print(f"All orders in picklist {picklist_id} are now dispatched. Picklist status updated to DISPATCH.")
                else:
                    print(f"Updated dispatch status for picklist {picklist_id}. {dispatch_status.dispatched_orders}/{dispatch_status.total_orders} orders dispatched.")
                
            except Picklist.DoesNotExist:
                print(f"Picklist {picklist_id} not found, skipping dispatch status update")
            except Exception as e:
                print(f"Error updating dispatch status: {str(e)}")
                traceback.print_exc()
                # Continue anyway - the order status is already updated
        
        # Prepare response
        response_data = {
            'status': 'success',
            'message': f'AWB number {awb} saved and order moved to Dispatch',
            'platform': platform,
            'updated': updated > 0,
            'order_number': order_number,
            'awb': awb,
            'order_status': 'Dispatch'  # Include the new status in response
        }
        
        # Include dispatch status info if available
        if dispatch_status:
            percentage = 0
            if dispatch_status.total_orders > 0:
                percentage = (dispatch_status.dispatched_orders / dispatch_status.total_orders) * 100
                
            response_data['dispatch_info'] = {
                'picklist_id': picklist_id,
                'total_orders': dispatch_status.total_orders,
                'dispatched_orders': dispatch_status.dispatched_orders,
                'percentage': round(percentage, 1),
                'is_fully_dispatched': dispatch_status.is_fully_dispatched
            }
        
        return JsonResponse(response_data)
    
    except Exception as e:
        print(f"Error in save_awb_and_dispatch: {str(e)}")
        traceback.print_exc()
        
        return JsonResponse({
            'status': 'error',
            'message': f'Error saving AWB number: {str(e)}'
        }, status=500)