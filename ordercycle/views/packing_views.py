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
from django.views.decorators.csrf import csrf_exempt
from ..models import (
    Picklist, PicklistItem, PicklistItemLocation, MasterTable,
    AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders,
    UserProfile,PicklistDispatchStatus,ImageUpload,PicklistSKUValidation
)


@require_http_methods(["GET"])
def search_picklist(request):
    """
    Enhanced: Search for a picklist by ID with quantity-based SKU validation status
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
            
            # Only include orders that are NOT in Dispatch status
            if order_status != 'Dispatch':
                # Get or create SKU validation record with quantity tracking
                sku_validation, created = PicklistSKUValidation.objects.get_or_create(
                    picklist=picklist,
                    sku=item.sku,
                    order_number=item.order_number,
                    defaults={
                        'validated': False,
                        'required_quantity': item.quantity,
                        'validated_quantity': 0
                    }
                )
                
                # Update required quantity if not set
                if created or sku_validation.required_quantity == 0:
                    sku_validation.required_quantity = item.quantity
                    sku_validation.save()
                
                items_data.append({
                    'id': item.id,
                    'order_number': item.order_number,
                    'sku': item.sku,
                    'quantity': item.quantity,
                    'location': location,
                    'picked': picked,
                    'picker_id': picker_id,
                    'awb': awb,
                    'order_status': order_status,
                    'validated': sku_validation.validated,
                    'validated_quantity': getattr(sku_validation, 'validated_quantity', 0),
                    'required_quantity': getattr(sku_validation, 'required_quantity', item.quantity),
                    'validation_progress': f"{getattr(sku_validation, 'validated_quantity', 0)}/{getattr(sku_validation, 'required_quantity', item.quantity)}"
                })
        
        # Get validation status (this might need to be updated to handle quantity-based validation)
        validation_status = picklist.get_validation_status()
        
        return JsonResponse({
            'status': 'success',
            'picklist': {
                'picklist_id': picklist.picklist_id,
                'picklist_type': picklist.picklist_type,
                'quantity': picklist.quantity,
                'status': picklist.status,
                'platform': picklist.platform,
                'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'items': items_data,
                'validation_status': validation_status
            }
        })
    
    except Picklist.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': f'Picklist with ID {picklist_id} not found or not in PACKING status'
        }, status=404)

# The issue is in your Django view - validate_sku function
# Here's the corrected version:

@csrf_exempt
@require_http_methods(["POST"])
def validate_sku(request):
    """
    FIXED: Mark a SKU as validated with proper quantity-based validation
    """
    try:
        data = json.loads(request.body)
        picklist_id = data.get('picklist_id')
        sku = data.get('sku')
        order_number = data.get('order_number')
        
        if not all([picklist_id, sku, order_number]):
            return JsonResponse({
                'status': 'error',
                'message': 'Picklist ID, SKU, and Order Number are required'
            }, status=400)
        
        # Get picklist
        picklist = get_object_or_404(Picklist, picklist_id=picklist_id)
        
        # Get the picklist item to know the required quantity
        picklist_item = PicklistItem.objects.filter(
            picklist=picklist,
            sku=sku,
            order_number=order_number
        ).first()
        
        if not picklist_item:
            return JsonResponse({
                'status': 'error',
                'message': f'SKU {sku} not found in order {order_number} for this picklist'
            }, status=404)
        
        required_quantity = picklist_item.quantity
        
        # Get or create SKU validation record with quantity tracking
        sku_validation, created = PicklistSKUValidation.objects.get_or_create(
            picklist=picklist,
            sku=sku,
            order_number=order_number,
            defaults={
                'validated': False,
                'required_quantity': required_quantity,
                'validated_quantity': 0
            }
        )
        
        # IMPORTANT: Update required_quantity if it was created before or is incorrect
        if sku_validation.required_quantity != required_quantity:
            sku_validation.required_quantity = required_quantity
        
        # CRITICAL FIX: Only increment if not already fully validated
        if sku_validation.validated_quantity < sku_validation.required_quantity:
            sku_validation.validated_quantity += 1
        else:
            # Already fully validated - don't increment further
            return JsonResponse({
                'status': 'warning',
                'message': f'SKU {sku} is already fully validated ({sku_validation.validated_quantity}/{sku_validation.required_quantity})',
                'validation_details': {
                    'sku': sku,
                    'order_number': order_number,
                    'validated_quantity': sku_validation.validated_quantity,
                    'required_quantity': sku_validation.required_quantity,
                    'is_fully_validated': True,
                    'remaining_quantity': 0
                }
            })
        
        # Check if all required quantity is NOW validated
        if sku_validation.validated_quantity >= sku_validation.required_quantity:
            sku_validation.validated = True
            sku_validation.validated_at = timezone.now()
            # Ensure we don't exceed required quantity
            sku_validation.validated_quantity = sku_validation.required_quantity
            message = f'SKU {sku} FULLY validated! All {sku_validation.required_quantity} pieces confirmed.'
        else:
            # IMPORTANT: Keep validated as False until all pieces are scanned
            sku_validation.validated = False
            remaining = sku_validation.required_quantity - sku_validation.validated_quantity
            message = f'SKU {sku} progress: {sku_validation.validated_quantity}/{sku_validation.required_quantity} pieces validated. {remaining} remaining.'
        
        sku_validation.save()
        
        # Get updated validation status for the entire picklist
        validation_status = picklist.get_validation_status()
        
        # Get validation status for this specific order
        order_validation_status = picklist.get_order_validation_status(order_number)
        
        return JsonResponse({
            'status': 'success',
            'message': message,
            'validation_details': {
                'sku': sku,
                'order_number': order_number,
                'validated_quantity': sku_validation.validated_quantity,
                'required_quantity': sku_validation.required_quantity,
                'is_fully_validated': sku_validation.validated,  # This should be False until all pieces scanned
                'remaining_quantity': sku_validation.required_quantity - sku_validation.validated_quantity
            },
            'validation_status': validation_status,
            'order_validation_status': order_validation_status,
            'all_validated': validation_status['all_validated'],
            'order_all_validated': order_validation_status['all_validated']
        })
    
    except Exception as e:
        print(f"Error in validate_sku: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Error validating SKU: {str(e)}'
        }, status=500)
    
    
@require_http_methods(["GET"])
def get_validation_status(request):
    """
    Get validation status for a picklist or specific order
    """
    picklist_id = request.GET.get('picklist_id', '')
    order_number = request.GET.get('order_number', '')
    
    if not picklist_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Picklist ID is required'
        }, status=400)
    
    try:
        picklist = get_object_or_404(Picklist, picklist_id=picklist_id)
        
        if order_number:
            # Get validation status for specific order
            validation_status = picklist.get_order_validation_status(order_number)
        else:
            # Get validation status for entire picklist
            validation_status = picklist.get_validation_status()
        
        return JsonResponse({
            'status': 'success',
            'validation_status': validation_status
        })
    
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error getting validation status: {str(e)}'
        }, status=500)

# Enhanced search_product function with order count and total quantity stats

@require_http_methods(["GET"])
def search_product(request):
    """
    Enhanced: Show number of orders and total quantity for the product in picklist
    """
    product_id = request.GET.get('product_id', '')
    picklist_id = request.GET.get('picklist_id', '')
    
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
        
        # Get product image
        image_upload = ImageUpload.objects.filter(file_name=f"{product_id}.jpg").first()
        
        if image_upload:
            import base64
            image_base64 = base64.b64encode(image_upload.image).decode('utf-8')
            image_url = f"data:{image_upload.content_type};base64,{image_base64}"
        else:
            image_url = "/static/images/no_image_found.jpg"
        
        # Enhanced SKU matching logic with statistics
        validation_info = None
        in_current_picklist = False
        matched_sku = None
        match_type = None
        picklist_stats = None  # NEW: Statistics for this product in picklist
        
        if picklist_id:
            try:
                picklist = Picklist.objects.get(picklist_id=picklist_id)
                master_sku = product.sku
                
                print(f"🔍 Searching for SKU: '{master_sku}' in picklist {picklist_id}")
                
                # STEP 1: Try exact match first
                exact_match_items = PicklistItem.objects.filter(
                    picklist=picklist, 
                    sku=master_sku
                )
                
                if exact_match_items.exists():
                    matched_items = exact_match_items
                    matched_sku = master_sku
                    match_type = "exact"
                    print(f"✅ EXACT MATCH found: {master_sku}")
                    
                else:
                    # STEP 2: Try normalized matching
                    print(f"❌ No exact match for '{master_sku}', trying normalized matching...")
                    
                    matched_sku, match_type = find_normalized_match(master_sku, picklist)
                    
                    if matched_sku:
                        matched_items = PicklistItem.objects.filter(
                            picklist=picklist, 
                            sku=matched_sku
                        )
                        print(f"✅ NORMALIZED MATCH found: '{matched_sku}'")
                    else:
                        matched_items = PicklistItem.objects.none()
                        print(f"❌ No match found for '{master_sku}'")
                
                # Process matched items if found
                if matched_items.exists():
                    in_current_picklist = True
                    
                    # NEW: Calculate picklist statistics
                    picklist_stats = calculate_picklist_stats(matched_items, matched_sku)
                    print(f"📊 Picklist stats: {picklist_stats}")
                    
                    # Build validation info using matched SKU
                    all_orders_with_sku = []
                    unvalidated_orders = []
                    
                    for item in matched_items.order_by('order_number'):
                        # Get or create validation record using matched SKU
                        sku_validation, created = PicklistSKUValidation.objects.get_or_create(
                            picklist=picklist,
                            sku=matched_sku,
                            order_number=item.order_number,
                            defaults={
                                'validated': False,
                                'required_quantity': item.quantity,
                                'validated_quantity': 0
                            }
                        )
                        
                        # Ensure correct quantity
                        if sku_validation.required_quantity != item.quantity:
                            sku_validation.required_quantity = item.quantity
                            sku_validation.save()
                        
                        order_info = {
                            'order_number': item.order_number,
                            'validated': sku_validation.validated,
                            'quantity': item.quantity,
                            'validated_quantity': sku_validation.validated_quantity,
                            'required_quantity': sku_validation.required_quantity,
                            'validation_progress': f"{sku_validation.validated_quantity}/{sku_validation.required_quantity}"
                        }
                        
                        all_orders_with_sku.append(order_info)
                        
                        if not sku_validation.validated:
                            unvalidated_orders.append(order_info)
                    
                    # Build validation info with enhanced statistics
                    if unvalidated_orders:
                        current_order = unvalidated_orders[0]
                        validation_info = {
                            'order_number': current_order['order_number'],
                            'validated': False,
                            'can_validate': True,
                            'quantity': current_order['quantity'],
                            'validated_quantity': current_order['validated_quantity'],
                            'required_quantity': current_order['required_quantity'],
                            'validation_progress': current_order['validation_progress'],
                            'total_orders_with_sku': len(all_orders_with_sku),
                            'validated_orders_count': len(all_orders_with_sku) - len(unvalidated_orders),
                            'remaining_orders': len(unvalidated_orders),
                            'progress_message': f"Order {current_order['order_number']} - Scan {current_order['validated_quantity']}/{current_order['required_quantity']} pieces ({len(unvalidated_orders)} orders remaining)"
                        }
                    else:
                        # All validated
                        validation_info = {
                            'order_number': all_orders_with_sku[0]['order_number'],
                            'validated': True,
                            'can_validate': False,
                            'quantity': all_orders_with_sku[0]['quantity'],
                            'validated_quantity': all_orders_with_sku[0]['required_quantity'],
                            'required_quantity': all_orders_with_sku[0]['required_quantity'],
                            'validation_progress': f"{all_orders_with_sku[0]['required_quantity']}/{all_orders_with_sku[0]['required_quantity']}",
                            'total_orders_with_sku': len(all_orders_with_sku),
                            'validated_orders_count': len(all_orders_with_sku),
                            'remaining_orders': 0,
                            'progress_message': f"All {len(all_orders_with_sku)} orders fully validated ✅"
                        }
                    
            except Picklist.DoesNotExist:
                pass
        
        # Build response with enhanced statistics
        response_data = {
            'status': 'success',
            'product': {
                'sku': matched_sku or product.sku,
                'original_sku': product.sku,
                'image_url': image_url,
                'location': product.location,
                'product_id': product.product_id,
                'box_no': product.box_no or '',
                'mrp': float(product.mrp) if product.mrp else 0,
                'generic_name': product.generic_name or '',
                'pack_check': product.pack_check or '',
                'pack_remarks': product.pack_remarks or ''
            },
            'in_current_picklist': in_current_picklist,
            'match_info': {
                'matched_sku': matched_sku,
                'match_type': match_type,
                'original_sku': product.sku
            } if matched_sku else None,
            'picklist_stats': picklist_stats  # NEW: Include picklist statistics
        }
        
        if validation_info:
            response_data['validation_info'] = validation_info
        
        return JsonResponse(response_data)
    
    except Exception as e:
        print(f"Error in search_product: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error searching for product: {str(e)}'
        }, status=500)


def calculate_picklist_stats(matched_items, sku):
    """
    Calculate statistics for a product in the picklist
    Returns: {
        'total_orders': int,
        'total_quantity': int,
        'order_details': [{'order_number': str, 'quantity': int}, ...],
        'unique_orders': int,
        'avg_quantity_per_order': float
    }
    """
    from django.db.models import Sum, Count
    
    if not matched_items.exists():
        return None
    
    # Calculate basic stats
    total_orders = matched_items.count()
    unique_orders = matched_items.values('order_number').distinct().count()
    total_quantity = matched_items.aggregate(total=Sum('quantity'))['total'] or 0
    
    # Get order details
    order_details = []
    for item in matched_items.order_by('order_number'):
        order_details.append({
            'order_number': item.order_number,
            'quantity': item.quantity
        })
    
    # Calculate average quantity per order
    avg_quantity_per_order = round(total_quantity / unique_orders, 2) if unique_orders > 0 else 0
    
    return {
        'total_orders': unique_orders,  # Number of unique orders
        'total_quantity': total_quantity,  # Total quantity across all orders
        'order_details': order_details,  # List of all orders with quantities
        'total_line_items': total_orders,  # Total line items (could be > unique orders if same order has multiple lines)
        'avg_quantity_per_order': avg_quantity_per_order
    }


# Keep the existing normalize functions
def find_normalized_match(master_sku, picklist):
    """
    Simple normalized matching: lowercase + remove all special characters
    """
    import re
    
    master_normalized = normalize_sku_simple(master_sku)
    print(f"🔄 Master SKU normalized: '{master_sku}' → '{master_normalized}'")
    
    all_picklist_skus = list(PicklistItem.objects.filter(
        picklist=picklist
    ).values_list('sku', flat=True).distinct())
    
    if not all_picklist_skus:
        return None, None
    
    for picklist_sku in all_picklist_skus:
        picklist_normalized = normalize_sku_simple(picklist_sku)
        
        if master_normalized == picklist_normalized:
            print(f"✅ NORMALIZED MATCH: '{master_sku}' → '{picklist_sku}'")
            return picklist_sku, "normalized"
    
    return None, None


def normalize_sku_simple(sku):
    """
    Simple normalization: convert to lowercase and remove all special characters
    """
    import re
    normalized = sku.lower()
    normalized = re.sub(r'[^a-z0-9]', '', normalized)
    return normalized

@csrf_exempt
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

@csrf_exempt
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
    from django.conf import settings
    from django.http import HttpResponse
    import base64
    
    sku = request.GET.get('sku')
    
    if not sku:
        return JsonResponse({'error': 'SKU parameter is required'}, status=400)
    
    try:
        # Query the database for a product with this SKU
        product = MasterTable.objects.filter(sku=sku).first()
        
        # Initialize variables
        product_id = ''
        image_data = None
        content_type = None
        
        if product:
            product_id = product.product_id or ''
            
            # Extract filename from the product's image_url (if available)
            if product.image_url:
                # Handle different formats: could be "ASINWISEIMAGES/B0CM5Z6HJG.jpg" or just "B0CM5Z6HJG.jpg"
                image_filename = os.path.basename(product.image_url)
            else:
                # If no image_url in product, try to use product_id as the filename
                image_filename = f"{product_id}.jpg" if product_id else f"{sku}.jpg"
        else:
            # If product not found, use SKU as filename
            image_filename = f"{sku}.jpg"
        # Check if image exists in database by filename
        image_upload = ImageUpload.objects.filter(file_name=image_filename).first()
        
        # If not found, try with product_id as filename
        if not image_upload and product_id:
            image_upload = ImageUpload.objects.filter(file_name=f"{product_id}.jpg").first()
            
        # If still not found, try with SKU as filename
        if not image_upload:
            image_upload = ImageUpload.objects.filter(file_name=f"{sku}.jpg").first()
        
        # Set image data and content type if found
        if image_upload:
            image_data = image_upload.image
            content_type = image_upload.content_type
            
            # Convert binary data to base64 string for JSON response
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            image_url = f"data:{content_type};base64,{image_base64}"
        else:
            # Use "NO PICTURE.jpg" as fallback
            default_image_path = os.path.join(settings.STATIC_ROOT, 'images', 'NO PICTURE.jpg')
            try:
                with open(default_image_path, 'rb') as f:
                    default_image_data = f.read()
                    # Convert binary data to base64 string for JSON response
                    image_base64 = base64.b64encode(default_image_data).decode('utf-8')
                    image_url = f"data:image/jpeg;base64,{image_base64}"
            except FileNotFoundError:
                # If default image file doesn't exist, fall back to static URL
                image_url = f"{settings.STATIC_URL}images/no_image_found.jpg"
        
        # Prepare and return product details with image URL
        response_data = {
            'sku': sku,
            'image_url': image_url,
            'product_id': product_id,
            'location': product.location if product else 'Unknown',
            'box_no': product.box_no or '' if product else '',
            'mrp': float(product.mrp) if product and product.mrp is not None else None,
            'generic_name': product.generic_name or f"Product (SKU: {sku})" if product else f"Product (SKU: {sku})",
            'pack_check': product.pack_check or '' if product else '',
            'pack_remarks': product.pack_remarks or '' if product else ''
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        print(f"Error retrieving product data: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'Error retrieving product data: {str(e)}'}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def save_awb_and_dispatch(request):
    """
    Validate the AWB number against existing records for an order.
    If the AWB matches what's already in the system, move the order to Complete status.
    If the AWB does not match, return an error.
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
        existing_awb = None
        
        # Try each platform table to find the order
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        for plat, model in model_mapping.items():
            order = model.objects.filter(order_number=order_number).first()
            if order:
                platform = plat
                existing_awb = order.AWB
                
                # Check if the order has an existing AWB that doesn't match the provided one
                if existing_awb and existing_awb.strip() and existing_awb.strip() != awb.strip():
                    return JsonResponse({
                        'status': 'error',
                        'message': f'AWB validation failed. The entered AWB ({awb}) does not match the existing AWB ({existing_awb}) for order {order_number}.',
                        'existing_awb': existing_awb
                    }, status=400)
                
                # If AWB matches or there isn't an existing AWB, update order status
                result = model.objects.filter(order_number=order_number).update(
                    AWB=awb,
                    status='Complete'  # Changed from 'Dispatch' to 'Complete'
                )
                updated = result
                
                # DELETE OrderPDF record for this order after marking as Complete
                try:
                    from ..models import OrderPDF
                    order_pdf = OrderPDF.objects.get(order_id=order_number)
                    order_pdf.delete()
                    print(f"Deleted OrderPDF record for order {order_number}")
                except OrderPDF.DoesNotExist:
                    print(f"No OrderPDF record found for order {order_number}")
                except Exception as pdf_error:
                    print(f"Error deleting OrderPDF for order {order_number}: {str(pdf_error)}")
                
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
            'message': f'AWB number {awb} verified and order moved to Complete',
            'platform': platform,
            'updated': updated > 0,
            'order_number': order_number,
            'awb': awb,
            'order_status': 'Complete',  # Update the status in the response as well
            'awb_match': True  # Indicate AWB validation was successful
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