"""
Views for handling printing and label-related functionality.
"""
import os
import json
import traceback
from django.utils import timezone
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.contrib.sites.shortcuts import get_current_site
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from ..models import (
    Picklist, PicklistItem, PicklistItemLocation, UserProfile,
    AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders,
    OrderPDF
)
from rest_framework.decorators import api_view
from rest_framework.response import Response

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


@csrf_exempt
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
        print(f"Error in save_printer_preferences: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error saving printer preferences: {str(e)}'
        }, status=500)

@api_view(['GET'])
def get_pending_print_jobs(request):
    """
    Get pending print jobs for a specific client
    """
    client_id = request.GET.get('client_id')
    
    # TODO: Add your actual logic here to fetch pending print jobs
    # For now, returning empty to stop the 404 errors
    
    return Response({
        'success': True,
        'pending_jobs': [],
        'client_id': client_id,
        'message': 'No pending print jobs'
    })

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
        print(f"Error in get_printer_preferences: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error getting printer preferences: {str(e)}'
        }, status=500)


@csrf_exempt
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
        print(f"Error in send_test_print: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error initiating test print: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def print_label(request):
    """
    Find and return the PDF URL for a specific order for printing.
    Gets the PDF directly from the OrderPDF model.
    """
    try:
        data = json.loads(request.body)
        platform = data.get('platform')
        order_number = data.get('order_number')
        
        if not platform or not order_number:
            return JsonResponse({
                'status': 'error',
                'message': 'Platform and order number are required'
            }, status=400)
        
        # Get the appropriate model based on platform
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        platform_upper = platform.upper()
        if platform_upper not in model_mapping:
            return JsonResponse({
                'status': 'error',
                'message': f'Unknown platform: {platform}'
            }, status=400)
            
        order = model_mapping[platform_upper].objects.filter(order_number=order_number).first()
        
        if not order:
            return JsonResponse({
                'status': 'error',
                'message': f'Order {order_number} not found'
            }, status=404)
        
        # Determine which page is the label page based on platform
        label_page_index = 0  # Default - first page is label
        
        if platform_upper == 'FIRSTCRY':
            # For FirstCry, the label is typically the last page
            label_page_index = -1  # Use -1 to indicate last page
        
        # Check if PDF exists in the OrderPDF model
        pdf_record = OrderPDF.objects.filter(order_id=order_number).first()
        
        if pdf_record:
            # PDF exists in database - create relative download URL
            print(f"DEBUG: Using PDF from database for order {order_number}")
            
            # Use relative URL to avoid CORS issues
            pdf_url = f"/api/orders/{order_number}/download/"
            
            return JsonResponse({
                'status': 'success',
                'pdf_url': pdf_url,
                'order_number': order.order_number,
                'awb': getattr(order, 'AWB', 'N/A'),
                'platform': platform,
                'label_page_index': label_page_index,
                'source': 'database'
            })
        
        # PDF not found in database - check if it exists in the file system via pdf_url
        if not order.pdf_url:
            return JsonResponse({
                'status': 'error',
                'message': f'No PDF file found for order {order_number}'
            }, status=404)
        
        # Get the PDF from the file system and save it to the database
        pdf_path = order.pdf_url
        
        # Check if it's a file path or URL
        if pdf_path.startswith('/') or pdf_path.startswith('C:'):
            # It's a file path
            if os.path.exists(pdf_path):
                try:
                    # Read the file
                    with open(pdf_path, 'rb') as f:
                        pdf_content = f.read()
                    
                    # Save to database
                    filename = os.path.basename(pdf_path)
                    OrderPDF.objects.create(
                        order_id=order_number,
                        pdf_content=pdf_content,
                        filename=filename,
                        source_type='file_import'
                    )
                    
                    print(f"DEBUG: Imported PDF from {pdf_path} to database")
                    
                    # Now create relative URL for the database version
                    pdf_url = f"/api/orders/{order_number}/download/"
                    
                    return JsonResponse({
                        'status': 'success',
                        'pdf_url': pdf_url,
                        'order_number': order.order_number,
                        'awb': getattr(order, 'AWB', 'N/A'),
                        'platform': platform,
                        'label_page_index': label_page_index,
                        'source': 'database_import'
                    })
                except Exception as e:
                    print(f"DEBUG: Error importing PDF to database: {str(e)}")
                    # Fall back to file URL
            else:
                print(f"DEBUG: PDF file not found at {pdf_path}")
        
        # If we get here, we couldn't import the PDF to the database
        # Fall back to the original file URL-based approach with relative URLs
        if pdf_path.startswith('/') or pdf_path.startswith('C:'):
            # Convert file path to relative URL
            filename = os.path.basename(pdf_path)
            
            # Determine platform-specific directory
            platform_dir_mapping = {
                'AMAZON': 'amazonPdfs',
                'FLIPKART': 'flipkartPdfs',
                'FIRSTCRY': 'firstcryPdfs',
                'MEESHO': 'meeshoPdfs'
            }
            
            pdf_url = f"/media/{platform_dir_mapping.get(platform_upper, 'orderPdfs')}/{filename}"
        else:
            # It's already a URL - make it relative
            pdf_url = pdf_path
            if not pdf_url.startswith('/'):
                pdf_url = '/' + pdf_url
        
        print(f"WARNING: Using file-based URL for PDF: {pdf_url}")
        
        return JsonResponse({
            'status': 'success',
            'pdf_url': pdf_url,
            'order_number': order.order_number,
            'awb': getattr(order, 'AWB', 'N/A'),
            'platform': platform,
            'label_page_index': label_page_index,
            'source': 'file'
        })
    
    except Exception as e:
        print(f"Error in print_label: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error processing print request: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def mark_order_as_printed(request):
    """
    Mark an order as printed/processed in the database.
    This updates both the order status in the platform-specific table
    and ensures the picklist item is marked as picked.
    """
    try:
        data = json.loads(request.body)
        picklist_id = data.get('picklist_id')
        order_number = data.get('order_number')
        
        if not picklist_id or not order_number:
            return JsonResponse({
                'status': 'error',
                'message': 'Picklist ID and order number are required'
            }, status=400)
        
        # Logging for debugging
        print(f"Marking order {order_number} in picklist {picklist_id} as printed")
        
        # Find the picklist
        try:
            picklist = Picklist.objects.get(picklist_id=picklist_id)
        except Picklist.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'Picklist {picklist_id} not found'
            }, status=404)
            
        # Find all picklist items with this order number
        items = PicklistItem.objects.filter(picklist=picklist, order_number=order_number)
        
        if not items.exists():
            return JsonResponse({
                'status': 'error',
                'message': f'Order {order_number} not found in picklist {picklist_id}'
            }, status=404)
            
        # Mark all matching items as picked/processed
        updated_count = 0
        for item in items:
            if not item.picked:  # Only update if not already picked
                item.picked = True
                item.save()
                updated_count += 1
                
                # Also update the PicklistItemLocation if it exists
                location_info, created = PicklistItemLocation.objects.get_or_create(
                    picklist_item=item,
                    defaults={'location': 'Unknown', 'picked': False}
                )
                location_info.picked = True
                location_info.picked_at = timezone.now()
                location_info.save()
        
        # Also update the status in the appropriate platform order table
        # First determine which platform this picklist belongs to
        platform = picklist.platform.upper() if picklist.platform else "UNKNOWN"
        
        # Find and update the order in the appropriate table
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        platform_updated = False
        if platform in model_mapping:
            orders_updated = model_mapping[platform].objects.filter(order_number=order_number).update(
                status='Processed'
            )
            platform_updated = orders_updated > 0
        
        # Check if all items in the picklist are now picked
        all_picked = not PicklistItem.objects.filter(picklist=picklist, picked=False).exists()
        
        # If all items are picked, update the picklist status if needed
        if all_picked and picklist.status == 'PACKING':
            picklist.status = 'PACKED'
            picklist.save()
        
        return JsonResponse({
            'status': 'success',
            'message': f'Order {order_number} marked as processed',
            'updated_items': updated_count,
            'platform_updated': platform_updated,
            'all_picked': all_picked
        })
        
    except Exception as e:
        print(f"Error in mark_order_as_printed: {str(e)}")
        traceback.print_exc()
        
        return JsonResponse({
            'status': 'error',
            'message': f'Error processing request: {str(e)}'
        }, status=500)
    
@csrf_exempt
@require_http_methods(["POST"])
def mark_multiple_orders_printed(request):
    """
    Mark multiple orders as printed/processed in the database.
    This updates both the order status in the platform-specific table
    and ensures the picklist items are marked as picked.
    """
    try:
        data = json.loads(request.body)
        picklist_id = data.get('picklist_id')
        order_numbers = data.get('order_numbers', [])
        
        if not picklist_id or not order_numbers:
            return JsonResponse({
                'status': 'error',
                'message': 'Picklist ID and order numbers are required'
            }, status=400)
        
        # Logging for debugging
        print(f"Marking {len(order_numbers)} orders in picklist {picklist_id} as printed")
        
        # Find the picklist
        try:
            picklist = Picklist.objects.get(picklist_id=picklist_id)
        except Picklist.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'Picklist {picklist_id} not found'
            }, status=404)
        
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
        total_updated_orders = 0
        platform_orders_updated = 0
        processed_orders = []
        
        # Process each order
        for order_number in order_numbers:
            # Find all picklist items with this order number
            items = PicklistItem.objects.filter(picklist=picklist, order_number=order_number)
            
            if not items.exists():
                print(f"Order {order_number} not found in picklist {picklist_id}")
                continue
            
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
            
            if order_updated_items > 0:
                total_updated_items += order_updated_items
                total_updated_orders += 1
                processed_orders.append(order_number)
                print(f"Order {order_number}: {order_updated_items} items marked as picked")
            
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
        
        return JsonResponse({
            'status': 'success',
            'message': f'Successfully processed {total_updated_orders} orders ({total_updated_items} items)',
            'total_updated_orders': total_updated_orders,
            'total_updated_items': total_updated_items,
            'platform_orders_updated': platform_orders_updated,
            'processed_orders': processed_orders,
            'all_picked': all_picked,
            'picklist_completed': picklist_status_updated
        })
        
    except Exception as e:
        print(f"Error in mark_multiple_orders_printed: {str(e)}")
        traceback.print_exc()
        
        return JsonResponse({
            'status': 'error',
            'message': f'Error processing request: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def save_awb_number(request):
    """
    Save the AWB number for an order across all applicable tables.
    This is called immediately after printing a label in the packing stage.
    """
    try:
        data = json.loads(request.body)
        order_number = data.get('order_number')
        awb = data.get('awb')
        picklist_id = data.get('picklist_id')  # Optional but helpful for logging
        
        if not order_number or not awb:
            return JsonResponse({
                'status': 'error',
                'message': 'Order number and AWB are required'
            }, status=400)
            
        # Logging for debugging
        print(f"Saving AWB {awb} for order {order_number} from picklist {picklist_id}")
        
        # First find the platform for this order
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
                # Update order
                updated = model.objects.filter(order_number=order_number).update(AWB=awb)
                break
                
        if not platform:
            return JsonResponse({
                'status': 'error',
                'message': f'Order {order_number} not found in any platform'
            }, status=404)
            
        # If picklist_id is provided, also update the AWB in picklist items
        picklist_items_updated = 0
        if picklist_id:
            try:
                # Get the picklist
                picklist = Picklist.objects.get(picklist_id=picklist_id)
                
                # Find all matching picklist items and update an AWB field if it exists
                # Note: If your PicklistItem model doesn't have an AWB field, you might need to add it
                items = PicklistItem.objects.filter(picklist=picklist, order_number=order_number)
                
                # Check if PicklistItem has an AWB field before attempting to update
                if hasattr(PicklistItem, 'awb'):
                    for item in items:
                        item.awb = awb
                        item.save()
                        picklist_items_updated += 1
                        
            except Picklist.DoesNotExist:
                # If picklist doesn't exist, just log it, don't fail the process
                print(f"Warning: Picklist {picklist_id} not found when saving AWB")
                pass
        
        return JsonResponse({
            'status': 'success',
            'message': f'AWB number {awb} saved for order {order_number}',
            'platform': platform,
            'platform_updated': updated > 0,
            'picklist_items_updated': picklist_items_updated
        })
    
    except Exception as e:
        print(f"Error in save_awb_number: {str(e)}")
        traceback.print_exc()
        
        return JsonResponse({
            'status': 'error',
            'message': f'Error saving AWB number: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def print_invoice(request):
    """
    Get the invoice PDF for a given order and AWB.
    Gets the PDF directly from the OrderPDF model.
    
    This function re-uses the same PDF as print_label since they are
    the same file, just different pages.
    """
    try:
        data = json.loads(request.body)
        platform = data.get('platform')
        order_number = data.get('order_number')
        awb = data.get('awb')
        exclude_label_page = data.get('exclude_label_page', True)
        
        if not platform or not (order_number or awb):
            return JsonResponse({
                'status': 'error',
                'message': 'Platform and either order number or AWB are required'
            }, status=400)
        
        # Find the order record from the appropriate model
        order = None
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        platform_upper = platform.upper()
        if platform_upper not in model_mapping:
            return JsonResponse({
                'status': 'error',
                'message': f'Unknown platform: {platform}'
            }, status=400)
            
        model = model_mapping[platform_upper]
        
        if order_number:
            order = model.objects.filter(order_number=order_number).first()
        elif awb:
            order = model.objects.filter(AWB=awb).first()
        
        if not order:
            return JsonResponse({
                'status': 'error',
                'message': f'Order not found for given parameters'
            }, status=404)
            
        # Get the order_number from the found order
        order_number = order.order_number
        
        # Determine which page is the label page based on platform
        # This is used by the client to know which pages to process
        label_page_index = 0  # Default - first page is label
        
        if platform_upper == 'FIRSTCRY':
            # For FirstCry, the label is typically the last page
            label_page_index = -1  # Use -1 to indicate last page
        
        # Check if PDF exists in the OrderPDF model
        pdf_record = OrderPDF.objects.filter(order_id=order_number).first()
        
        if pdf_record:
            # PDF exists in database - create relative download URL (FIXED)
            print(f"DEBUG: Using PDF from database for invoice {order_number}")
            
            # Use relative URL to avoid CORS issues
            pdf_url = f"/api/orders/{order_number}/download/"
            
            return JsonResponse({
                'status': 'success',
                'pdf_url': pdf_url,
                'order_number': order.order_number,
                'awb': getattr(order, 'AWB', 'N/A'),
                'platform': platform,
                'label_page_index': label_page_index,
                'source': 'database'
            })
        
        # If we reach this point, we need to do the same thing as print_label
        # to get the PDF URL from the file system and optionally import it
        
        # PDF not found in database - check if it exists in the file system via pdf_url
        if not order.pdf_url:
            return JsonResponse({
                'status': 'error',
                'message': f'No PDF file found for order {order_number}'
            }, status=404)
        
        # Get the PDF from the file system and save it to the database
        pdf_path = order.pdf_url
        
        # Check if it's a file path or URL
        if pdf_path.startswith('/') or pdf_path.startswith('C:'):
            # It's a file path
            if os.path.exists(pdf_path):
                try:
                    # Read the file
                    with open(pdf_path, 'rb') as f:
                        pdf_content = f.read()
                    
                    # Save to database
                    filename = os.path.basename(pdf_path)
                    OrderPDF.objects.create(
                        order_id=order_number,
                        pdf_content=pdf_content,
                        filename=filename,
                        source_type='file_import'
                    )
                    
                    print(f"DEBUG: Imported PDF from {pdf_path} to database")
                    
                    # Now create relative URL for the database version (FIXED)
                    pdf_url = f"/api/orders/{order_number}/download/"
                    
                    return JsonResponse({
                        'status': 'success',
                        'pdf_url': pdf_url,
                        'order_number': order.order_number,
                        'awb': getattr(order, 'AWB', 'N/A'),
                        'platform': platform,
                        'label_page_index': label_page_index,
                        'source': 'database_import'
                    })
                except Exception as e:
                    print(f"DEBUG: Error importing PDF to database: {str(e)}")
                    # Fall back to file URL
            else:
                print(f"DEBUG: PDF file not found at {pdf_path}")
        
        # If we get here, we couldn't import the PDF to the database
        # Fall back to the original file URL-based approach with relative URLs (FIXED)
        if pdf_path.startswith('/') or pdf_path.startswith('C:'):
            # Convert file path to relative URL
            filename = os.path.basename(pdf_path)
            
            # Determine platform-specific directory
            platform_dir_mapping = {
                'AMAZON': 'amazonPdfs',
                'FLIPKART': 'flipkartPdfs',
                'FIRSTCRY': 'firstcryPdfs',
                'MEESHO': 'meeshoPdfs'
            }
            
            pdf_url = f"/media/{platform_dir_mapping.get(platform_upper, 'orderPdfs')}/{filename}"
        else:
            # It's already a URL - make it relative
            pdf_url = pdf_path
            if not pdf_url.startswith('/'):
                pdf_url = '/' + pdf_url
        
        print(f"WARNING: Using file-based URL for PDF: {pdf_url}")
        
        return JsonResponse({
            'status': 'success',
            'pdf_url': pdf_url,
            'order_number': order.order_number,
            'awb': getattr(order, 'AWB', 'N/A'),
            'platform': platform,
            'label_page_index': label_page_index,
            'source': 'file'
        })
    
    except Exception as e:
        print(f"Error in print_invoice: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error processing print request: {str(e)}'
        }, status=500)

@require_http_methods(["GET"])
def download_pdf(request, order_id):
    """
    Stream PDF content directly from the database.
    This serves the same PDF for both label and invoice - the client
    handles which pages to display/print.
    """
    try:
        # Find PDF in database
        pdf_record = OrderPDF.objects.filter(order_id=order_id).first()
        
        if not pdf_record:
            return JsonResponse({
                'status': 'error',
                'message': f'PDF for order {order_id} not found in database'
            }, status=404)
        
        # Get filename or use default
        filename = pdf_record.filename or f"order_{order_id}.pdf"
        
        # Create response with PDF content
        response = HttpResponse(pdf_record.pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        # Add CORS headers manually to the PDF response
        origin = request.META.get('HTTP_ORIGIN')
        if origin and origin in [
            'http://192.168.240.29:8080',
            'http://192.168.240.29',
            'http://localhost:8080',
            'http://localhost',
            'http://127.0.0.1:8080',
            'http://127.0.0.1'
        ]:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = 'true'
        
        return response
        
    except Exception as e:
        print(f"Error in download_pdf: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error retrieving PDF: {str(e)}'
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
    model_mapping = {
        'AMAZON': AmazonOrders,
        'FLIPKART': FlipkarOrders,
        'FIRSTCRY': FirstcryOrders,
        'MEESHO': MeeshoOrders
    }
    
    order = None
    platform = None
    
    for plat, model in model_mapping.items():
        order_obj = model.objects.filter(AWB=awb).first()
        if order_obj:
            order = order_obj
            platform = plat
            break
    
    if not order:
        return JsonResponse({
            'status': 'error',
            'message': f'No order found with AWB {awb}'
        }, status=404)
    
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