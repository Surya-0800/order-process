"""
Views for handling packing stage functionality.
"""
import os
import json
import traceback
from pathlib import Path
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
    Enhanced search for a picklist by ID with quantity-based validation status
    Now allows searching for picklists in PACKING, COMPLETED, or DISPATCH status
    to handle processed orders that still need AWB verification
    """
    picklist_id = request.GET.get('picklist_id', '')
    if not picklist_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Picklist ID is required'
        }, status=400)
    
    try:
        # FIXED: Allow multiple statuses - not just PACKING
        # This allows access to picklists that have progressed beyond packing
        picklist = Picklist.objects.get(
            picklist_id=picklist_id, 
            status__in=['PACKING', 'COMPLETED', 'DISPATCH']
        )
        
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
            
            # Check order status across platforms
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
            
            # IMPORTANT: Only exclude 'Dispatch' orders
            # Keep Complete, Processed, and other statuses visible
            if order_status != 'Dispatch':
                # Get product_id from master table
                product = MasterTable.objects.filter(sku=item.sku).first()
                product_id = product.product_id if product else None
                
                # Get or create enhanced SKU validation record
                sku_validation, created = PicklistSKUValidation.objects.get_or_create(
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
                
                # Update existing record if needed
                if not created:
                    update_needed = False
                    if sku_validation.quantity != item.quantity:
                        sku_validation.quantity = item.quantity
                        update_needed = True
                    if not sku_validation.product_id and product_id:
                        sku_validation.product_id = product_id
                        update_needed = True
                    
                    # Recalculate validated status based on count vs quantity
                    new_validated_status = sku_validation.validated_count >= sku_validation.quantity
                    if sku_validation.validated != new_validated_status:
                        sku_validation.validated = new_validated_status
                        update_needed = True
                    
                    if update_needed:
                        sku_validation.save()
                
                # Get validation progress details
                validation_progress = sku_validation.get_validation_progress()
                
                # Add is_sku_complete flag for frontend logic
                is_sku_complete = sku_validation.is_fully_validated()
                
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
                    'is_sku_complete': is_sku_complete,
                    'product_id': sku_validation.product_id,
                    'validation_progress': validation_progress,
                    'validated_count': sku_validation.validated_count,
                    'required_quantity': sku_validation.quantity
                })
        
        # Get enhanced validation status
        validation_status = picklist.get_validation_status()
        
        # ENHANCED: Check if all remaining orders are dispatched
        all_orders_dispatched = len(items_data) == 0
        
        # Add no-cache headers to prevent browser caching
        response = JsonResponse({
            'status': 'success',
            'picklist': {
                'picklist_id': picklist.picklist_id,
                'picklist_type': picklist.picklist_type,
                'quantity': picklist.quantity,
                'status': picklist.status,
                'platform': picklist.platform,
                'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'items': items_data,
                'validation_status': validation_status,
                'all_orders_dispatched': all_orders_dispatched,
                'last_updated': timezone.now().isoformat()
            }
        })
        
        # Prevent caching to ensure fresh data
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        return response
    
    except Picklist.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': f'Picklist with ID {picklist_id} not found or has been fully processed (all orders dispatched)'
        }, status=404)
    except Exception as e:
        print(f"Error in search_picklist: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error searching picklist: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def validate_sku(request):
    """
    Enhanced SKU validation with quantity-based validation counting
    """
    try:
        data = json.loads(request.body)
        picklist_id = data.get('picklist_id')
        sku = data.get('sku')
        order_number = data.get('order_number')
        validation_mode = data.get('validation_mode', 'order_specific')
        
        if not all([picklist_id, sku]):
            return JsonResponse({
                'status': 'error',
                'message': 'Picklist ID and SKU are required'
            }, status=400)
        
        # Get picklist
        picklist = get_object_or_404(Picklist, picklist_id=picklist_id)
        
        # Get user if authenticated
        user = request.user if request.user.is_authenticated else None
        
        if validation_mode == 'order_specific' and order_number:
            # SCENARIO A: Order-specific validation (from image click or order view)
            result = _validate_sku_for_specific_order(picklist, sku, order_number, user)
        else:
            # SCENARIO B: Product search validation (find any unvalidated order)
            result = _validate_sku_any_order(picklist, sku, user)
        
        if result['status'] == 'error':
            return JsonResponse(result, status=400)
        
        # Get updated validation statuses
        validation_status = picklist.get_validation_status()
        
        response_data = {
            'status': 'success',
            'message': result['message'],
            'validation_details': result['validation_details'],
            'validation_status': validation_status,
            'all_validated': validation_status['all_validated']
        }
        
        # Add order validation status if order_number is provided
        if order_number:
            order_validation_status = picklist.get_order_validation_status(order_number)
            response_data['order_validation_status'] = order_validation_status
            response_data['order_all_validated'] = order_validation_status['all_validated']
        
        return JsonResponse(response_data)
    
    except Exception as e:
        print(f"Error in validate_sku: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error validating SKU: {str(e)}'
        }, status=500)  
    

def _validate_sku_for_specific_order(picklist, sku, order_number, user=None):
    """
    Enhanced validation with automatic creation of missing validation records
    """
    try:
        print(f"Looking for PicklistItem: picklist={picklist.picklist_id}, sku={sku}, order={order_number}")
        
        # Get the picklist item to ensure it exists
        picklist_item = PicklistItem.objects.filter(
            picklist=picklist,
            sku=sku,
            order_number=order_number
        ).first()
        
        if not picklist_item:
            # Enhanced debugging info
            all_skus_in_picklist = list(PicklistItem.objects.filter(picklist=picklist).values_list('sku', flat=True).distinct())
            all_orders_in_picklist = list(PicklistItem.objects.filter(picklist=picklist).values_list('order_number', flat=True).distinct())
            items_with_sku = list(PicklistItem.objects.filter(picklist=picklist, sku=sku).values_list('order_number', flat=True))
            items_with_order = list(PicklistItem.objects.filter(picklist=picklist, order_number=order_number).values_list('sku', flat=True))
            
            error_details = {
                'message': f'SKU {sku} not found in order {order_number} for picklist {picklist.picklist_id}',
                'debug_info': {
                    'total_skus_in_picklist': len(all_skus_in_picklist),
                    'total_orders_in_picklist': len(all_orders_in_picklist),
                    'orders_with_this_sku': items_with_sku[:5],
                    'skus_in_this_order': items_with_order[:5],
                    'requested_sku': sku,
                    'requested_order': order_number
                }
            }
            
            print(f"PicklistItem not found. Debug info: {error_details['debug_info']}")
            
            return {
                'status': 'error',
                'message': error_details['message'],
                'debug_info': error_details['debug_info']
            }
        
        print(f"PicklistItem found: qty={picklist_item.quantity}, picked={picklist_item.picked}")
        
        # Get product_id from master table
        product = MasterTable.objects.filter(sku=sku).first()
        product_id = product.product_id if product else None
        
        # ENHANCED: Always try to get or create validation record
        # This handles cases where the signal didn't fire or records are missing
        validation_record, created = PicklistSKUValidation.objects.get_or_create(
            picklist=picklist,
            sku=sku,
            order_number=order_number,
            defaults={
                'validated': False,
                'quantity': picklist_item.quantity,
                'validated_count': 0,
                'product_id': product_id
            }
        )
        
        if created:
            print(f"Created missing validation record for {sku} in order {order_number}")
        else:
            print(f"Found existing validation record: count={validation_record.validated_count}, qty={validation_record.quantity}")
        
        # Update record if needed (ensure data consistency)
        update_needed = False
        if validation_record.quantity != picklist_item.quantity:
            print(f"Updating quantity from {validation_record.quantity} to {picklist_item.quantity}")
            validation_record.quantity = picklist_item.quantity
            update_needed = True
            
        if not validation_record.product_id and product_id:
            print(f"Adding missing product_id: {product_id}")
            validation_record.product_id = product_id
            update_needed = True
            
        # Recalculate validated status based on count vs quantity
        new_validated_status = validation_record.validated_count >= validation_record.quantity
        if validation_record.validated != new_validated_status:
            print(f"Updating validated status from {validation_record.validated} to {new_validated_status}")
            validation_record.validated = new_validated_status
            update_needed = True
        
        if update_needed:
            validation_record.save()
            print(f"Saved updates to validation record")
        
        # Check if already fully validated
        if validation_record.is_fully_validated():
            return {
                'status': 'error',
                'message': f'SKU {sku} is already fully validated for order {order_number} ({validation_record.validated_count}/{validation_record.quantity})',
                'validation_details': validation_record.get_validation_progress()
            }
        
        # Increment validation count
        success = validation_record.increment_validation(user)
        
        if not success:
            return {
                'status': 'error',
                'message': f'Failed to validate SKU {sku} (already at max count)',
                'validation_details': validation_record.get_validation_progress()
            }
        
        # Prepare response message
        progress = validation_record.get_validation_progress()
        if validation_record.is_fully_validated():
            message = f'SKU {sku} fully validated for order {order_number}! ({progress["validated_count"]}/{progress["required_quantity"]})'
        else:
            message = f'SKU {sku} validation progress: {progress["validated_count"]}/{progress["required_quantity"]} for order {order_number}'
        
        print(f"Validation successful: {message}")
        
        return {
            'status': 'success',
            'message': message,
            'validation_details': progress
        }
        
    except Exception as e:
        print(f"Error in _validate_sku_for_specific_order: {str(e)}")
        traceback.print_exc()
        return {
            'status': 'error',
            'message': f'Error validating SKU for specific order: {str(e)}'
        }
    

def _validate_sku_any_order(picklist, sku, user=None):
    """
    Enhanced product search validation with automatic record creation
    """
    try:
        print(f"Looking for any unvalidated orders with SKU {sku} in picklist {picklist.picklist_id}")
        
        # First, ensure all PicklistItems for this SKU have validation records
        picklist_items = PicklistItem.objects.filter(picklist=picklist, sku=sku)
        
        if not picklist_items.exists():
            return {
                'status': 'error',
                'message': f'SKU {sku} not found in picklist {picklist.picklist_id}'
            }
        
        # Create missing validation records for this SKU
        created_records = 0
        for item in picklist_items:
            product = MasterTable.objects.filter(sku=sku).first()
            product_id = product.product_id if product else None
            
            validation_record, created = PicklistSKUValidation.objects.get_or_create(
                picklist=picklist,
                sku=sku,
                order_number=item.order_number,
                defaults={
                    'validated': False,
                    'quantity': item.quantity,
                    'validated_count': 0,
                    'product_id': product_id
                }
            )
            
            if created:
                created_records += 1
                print(f"Created validation record for {sku} in order {item.order_number}")
            else:
                # Ensure data consistency
                update_needed = False
                if validation_record.quantity != item.quantity:
                    validation_record.quantity = item.quantity
                    update_needed = True
                if not validation_record.product_id and product_id:
                    validation_record.product_id = product_id
                    update_needed = True
                    
                new_validated_status = validation_record.validated_count >= validation_record.quantity
                if validation_record.validated != new_validated_status:
                    validation_record.validated = new_validated_status
                    update_needed = True
                    
                if update_needed:
                    validation_record.save()
        
        if created_records > 0:
            print(f"Created {created_records} missing validation records")
        
        # Now find unvalidated records
        unvalidated_records = PicklistSKUValidation.objects.filter(
            picklist=picklist,
            sku=sku,
            validated=False
        ).order_by('order_number')
        
        if not unvalidated_records.exists():
            return {
                'status': 'error',
                'message': f'All orders with SKU {sku} are already fully validated',
                'validation_details': {'all_orders_validated': True}
            }
        
        # Get the first unvalidated record (sequential processing)
        target_record = unvalidated_records.first()
        
        # Increment validation count
        success = target_record.increment_validation(user)
        
        if not success:
            return {
                'status': 'error',
                'message': f'Failed to validate SKU {sku} (already at max count)',
                'validation_details': target_record.get_validation_progress()
            }
        
        # Prepare response message with progress info
        progress = target_record.get_validation_progress()
        total_orders_with_sku = PicklistSKUValidation.objects.filter(
            picklist=picklist, 
            sku=sku
        ).count()
        validated_orders_count = PicklistSKUValidation.objects.filter(
            picklist=picklist, 
            sku=sku, 
            validated=True
        ).count()
        remaining_orders = total_orders_with_sku - validated_orders_count
        
        if target_record.is_fully_validated():
            if remaining_orders > 0:
                message = f'Order {target_record.order_number} completed! SKU {sku} validation: {validated_orders_count}/{total_orders_with_sku} orders done'
            else:
                message = f'All orders with SKU {sku} are now fully validated!'
        else:
            message = f'SKU {sku} progress in order {target_record.order_number}: {progress["validated_count"]}/{progress["required_quantity"]} (Order {validated_orders_count + 1}/{total_orders_with_sku})'
        
        print(f"Product search validation successful: {message}")
        
        return {
            'status': 'success',
            'message': message,
            'validation_details': {
                **progress,
                'current_order': target_record.order_number,
                'total_orders_with_sku': total_orders_with_sku,
                'validated_orders_count': validated_orders_count,
                'remaining_orders': remaining_orders
            }
        }
        
    except Exception as e:
        print(f"Error in _validate_sku_any_order: {str(e)}")
        traceback.print_exc()
        return {
            'status': 'error',
            'message': f'Error validating SKU for any order: {str(e)}'
        }
    
    
@require_http_methods(["GET"])
def get_validation_status(request):
    """
    Enhanced validation status endpoint
    """
    picklist_id = request.GET.get('picklist_id', '')
    order_number = request.GET.get('order_number', '')
    sku = request.GET.get('sku', '')
    
    if not picklist_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Picklist ID is required'
        }, status=400)
    
    try:
        picklist = get_object_or_404(Picklist, picklist_id=picklist_id)
        
        response_data = {'status': 'success'}
        
        if sku and order_number:
            # Get validation status for specific SKU in specific order
            validation_record = PicklistSKUValidation.objects.filter(
                picklist=picklist,
                sku=sku,
                order_number=order_number
            ).first()
            
            if validation_record:
                response_data['validation_details'] = validation_record.get_validation_progress()
            else:
                response_data['validation_details'] = {
                    'validated_count': 0,
                    'required_quantity': 1,
                    'is_complete': False,
                    'percentage': 0
                }
        
        if order_number:
            # Get validation status for specific order
            validation_status = picklist.get_order_validation_status(order_number)
            response_data['validation_status'] = validation_status
        else:
            # Get validation status for entire picklist
            validation_status = picklist.get_validation_status()
            response_data['validation_status'] = validation_status
        
        return JsonResponse(response_data)
    
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error getting validation status: {str(e)}'
        }, status=500)
    

@require_http_methods(["GET"])
def search_product(request):
    """
    Enhanced sequential validation logic with quantity-based validation
    Now supports searching by product_id OR sku
    """
    search_query = request.GET.get('product_id', '')
    picklist_id = request.GET.get('picklist_id', '')
    
    if not search_query:
        return JsonResponse({
            'status': 'error',
            'message': 'Product ID or SKU is required'
        }, status=400)
    
    try:
        # Enhanced search: Try to find product by product_id OR sku
        from django.db.models import Q
        
        product = MasterTable.objects.filter(
            Q(product_id=search_query) | Q(sku=search_query)
        ).first()
        
        if not product:
            return JsonResponse({
                'status': 'error',
                'message': f'Product with ID/SKU "{search_query}" not found'
            }, status=404)
        
        # Check if image exists on file system
        image_url = _get_product_image_url(product.product_id)
        
        # Enhanced sequential validation logic
        validation_info = None
        in_current_picklist = False
        
        if picklist_id:
            try:
                picklist = Picklist.objects.get(picklist_id=picklist_id)
                
                # Find ALL orders with this SKU in the picklist
                picklist_items = PicklistItem.objects.filter(
                    picklist=picklist, 
                    sku=product.sku,
                    picked=False
                ).order_by('order_number')
                
                if picklist_items.exists():
                    in_current_picklist = True
                    
                    # Create/update validation records for all orders with this SKU
                    all_orders_with_sku = []
                    orders_needing_validation = []
                    
                    for item in picklist_items:
                        # Get or create validation record with enhanced fields
                        sku_validation, created = PicklistSKUValidation.objects.get_or_create(
                            picklist=picklist,
                            sku=product.sku,
                            order_number=item.order_number,
                            defaults={
                                'validated': False,
                                'quantity': item.quantity,
                                'validated_count': 0,
                                'product_id': product.product_id
                            }
                        )
                        
                        # Update existing record if needed
                        if not created:
                            update_needed = False
                            if sku_validation.quantity != item.quantity:
                                sku_validation.quantity = item.quantity
                                update_needed = True
                            if not sku_validation.product_id:
                                sku_validation.product_id = product.product_id
                                update_needed = True
                            
                            # Recalculate validated status
                            new_validated_status = sku_validation.validated_count >= sku_validation.quantity
                            if sku_validation.validated != new_validated_status:
                                sku_validation.validated = new_validated_status
                                update_needed = True
                                
                            if update_needed:
                                sku_validation.save()
                        
                        order_info = {
                            'order_number': item.order_number,
                            'validated': sku_validation.validated,
                            'quantity': sku_validation.quantity,
                            'validated_count': sku_validation.validated_count,
                            'validation_progress': sku_validation.get_validation_progress()
                        }
                        
                        all_orders_with_sku.append(order_info)
                        
                        if not sku_validation.validated:
                            orders_needing_validation.append(order_info)
                    
                    # ENHANCED SEQUENTIAL LOGIC: Return the first order needing validation
                    if orders_needing_validation:
                        # Show first order needing validation
                        current_order = orders_needing_validation[0]
                        validation_info = {
                            'order_number': current_order['order_number'],
                            'validated': False,
                            'can_validate': True,
                            'quantity': current_order['quantity'],
                            'validated_count': current_order['validated_count'],
                            'validation_progress': current_order['validation_progress'],
                            'total_orders_with_sku': len(all_orders_with_sku),
                            'validated_orders_count': len(all_orders_with_sku) - len(orders_needing_validation),
                            'remaining_orders': len(orders_needing_validation),
                            'progress_message': f"Order {current_order['order_number']} - {current_order['validated_count']}/{current_order['quantity']} validated ({len(orders_needing_validation)} orders remaining)"
                        }
                    else:
                        # All orders are fully validated
                        validation_info = {
                            'order_number': all_orders_with_sku[0]['order_number'],
                            'validated': True,
                            'can_validate': False,
                            'quantity': all_orders_with_sku[0]['quantity'],
                            'validated_count': all_orders_with_sku[0]['validated_count'],
                            'validation_progress': all_orders_with_sku[0]['validation_progress'],
                            'total_orders_with_sku': len(all_orders_with_sku),
                            'validated_orders_count': len(all_orders_with_sku),
                            'remaining_orders': 0,
                            'progress_message': f"All {len(all_orders_with_sku)} orders fully validated"
                        }
                    
            except Picklist.DoesNotExist:
                pass
        
        # Return enhanced product details
        response_data = {
            'status': 'success',
            'product': {
                'sku': product.sku,
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
            'search_query': search_query,
            'found_by': 'product_id' if product.product_id == search_query else 'sku'
        }
        
        if validation_info:
            response_data['validation_info'] = validation_info
        
        return JsonResponse(response_data)
    
    except Exception as e:
        print(f"Error in search_product: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error searching for product: {str(e)}'
        }, status=500)  


@csrf_exempt
@require_http_methods(["POST"])
def mark_picklist_completed(request, picklist_id):
    """
    Mark a picklist as completed
    """
    try:
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
            
            packed_items += 1
        
        # Check if all items are now packed
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
    """
    try:
        picklist = Picklist.objects.get(picklist_id=picklist_id)
        
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
        
        # Initialize variables
        product_id = ''
        
        if product:
            product_id = product.product_id or ''
        
        # Get image URL using helper function
        image_url = _get_product_image_url(product_id if product else sku)
        
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
        picklist_id = data.get('picklist_id')
        
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
                    status='Complete'
                )
                updated = result
                
                # DELETE OrderPDF record for this order after marking as Complete
                try:
                    from ..models import OrderPDF
                    order_pdf = OrderPDF.objects.get(order_id=order_number)
                    order_pdf.deleteƒ()
                    print(f"Deleted OrderPDF record for order {order_number}")
                except OrderPDF.DoesNotExist:
                    print(f"No OrderPDF record found for order {order_number}")
                except Exception as pdf_error:
                    print(f"Error deleting OrderPDF for order {order_number}: {str(pdf_error)}")
                
                # Verify the update was successful
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
                    print(f"All orders in picklist {picklist_id} are now dispatched. Picklist status updated to DISPATCH.")
                else:
                    print(f"Updated dispatch status for picklist {picklist_id}. {dispatch_status.dispatched_orders}/{dispatch_status.total_orders} orders dispatched.")
                
            except Picklist.DoesNotExist:
                print(f"Picklist {picklist_id} not found, skipping dispatch status update")
            except Exception as e:
                print(f"Error updating dispatch status: {str(e)}")
                traceback.print_exc()
        
        # Prepare response
        response_data = {
            'status': 'success',
            'message': f'AWB number {awb} verified and order moved to Complete',
            'platform': platform,
            'updated': updated > 0,
            'order_number': order_number,
            'awb': awb,
            'order_status': 'Complete',
            'awb_match': True
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


import unicodedata
from pathlib import Path
from django.conf import settings
import os


import os
import sys
import unicodedata
from pathlib import Path
from django.conf import settings

def _get_product_image_url(identifier):
    """
    Cross-platform image URL resolver (macOS, Linux, Windows).
    Handles Unicode normalization, case-insensitive matching,
    and macOS filesystem quirks like decomposed filenames.
    """
    product_images_dir = Path(settings.MEDIA_ROOT) / 'product_images'

    # Return default if the directory doesn't exist
    if not product_images_dir.exists():
        return f"{settings.STATIC_URL}images/no_image_found.jpg"

    try:
        # Normalize identifier depending on OS
        norm_form = "NFD" if sys.platform == "darwin" else "NFC"
        identifier_normalized = unicodedata.normalize(norm_form, str(identifier))
        identifier_lower = os.path.splitext(identifier_normalized.lower().strip())[0]

        for entry in os.scandir(product_images_dir):
            # Skip system/hidden files
            if entry.name.startswith('.') or not entry.is_file() or entry.name.lower() == '.ds_store':
                continue

            filename_normalized = unicodedata.normalize(norm_form, entry.name)
            name_without_ext, ext = os.path.splitext(filename_normalized)
            name_lower = name_without_ext.lower().strip()

            # Match by name (ignoring case and extension)
            if name_lower == identifier_lower:
                return f"{settings.MEDIA_URL}product_images/{entry.name}"

        # No match found
        return f"{settings.STATIC_URL}images/no_image_found.jpg"

    except Exception as e:
        print(f"[ERROR] _get_product_image_url failed: {e}")
        import traceback
        traceback.print_exc()
        return f"{settings.STATIC_URL}images/no_image_found.jpg"
