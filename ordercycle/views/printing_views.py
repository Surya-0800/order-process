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
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from ..models import (
    Picklist, PicklistItem, PicklistItemLocation, UserProfile,
    AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders
)

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
        print(f"Error in send_test_print: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error initiating test print: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
def print_label(request):
    """
    Find and return the PDF URL for a specific order for printing
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
        # Variable to store the actual file path for later
        actual_file_path = None
        
        # Case 1: If it's a full file system path (Windows or Unix)
        if pdf_path.startswith('C:') or pdf_path.startswith('/'):
            # Get just the filename from the path
            filename = os.path.basename(pdf_path)
            print(f"DEBUG: Extracted filename: {filename}")
            
            # Determine which directory it belongs to based on platform
            platform_dir_mapping = {
                'AMAZON': 'amazonPdfs',
                'FLIPKART': 'flipkartPdfs',
                'FIRSTCRY': 'firstcryPdfs',
                'MEESHO': 'meeshoPdfs'
            }
            
            pdf_url = f"{platform_dir_mapping.get(platform_upper, 'orderPdfs')}/{filename}"
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
                    for dirpath, dirnames, filenames in os.walk(settings.MEDIA_ROOT):
                        if filename in filenames:
                            alternate_path = os.path.join(dirpath, filename)
                            print(f"DEBUG: Found file in alternate location: {alternate_path}")
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
        
        # Make sure pdf_url starts with /media/ for proper URL construction
        if not pdf_url.startswith('/media/'):
            pdf_url = '/media/' + pdf_url.lstrip('/')
        
        # Convert to absolute URL
        current_site = get_current_site(request)
        domain = current_site.domain
        print(f"DEBUG: Domain from site: {domain}")
        protocol = 'https' if request.is_secure() else 'http'
        
        absolute_url = f"{protocol}://{domain}{pdf_url}"
        print(f"DEBUG: Final absolute URL: {absolute_url}")
        
        # Prepare the response
        response_data = {
            'status': 'success',
            'pdf_url': absolute_url,
            'order_number': order.order_number,
            'awb': getattr(order, 'AWB', 'N/A'),
            'platform': platform
        }
        
        # Include the direct file path if it exists
        if actual_file_path and os.path.exists(actual_file_path):
            response_data['file_path'] = actual_file_path
            print(f"DEBUG: Including file path in response: {actual_file_path}")
        
        return JsonResponse(response_data)
    
    except Exception as e:
        print(f"Error in print_label: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error processing print request: {str(e)}'
        }, status=500)


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


@require_http_methods(["POST"])
def print_invoice(request):
    """
    Get the invoice PDF for a given order and AWB, excluding the label page.
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
        
        # Get the PDF path from the order
        pdf_path = order.pdf_url
        
        if not pdf_path:
            return JsonResponse({
                'status': 'error',
                'message': f'No PDF file found for this order'
            }, status=404)
        
        # Determine which page is the label page based on platform
        label_page_index = 0  # Default - first page is label
        
        if platform_upper == 'FIRSTCRY':
            # For FirstCry, the label is typically the last page
            import fitz  # PyMuPDF
            try:
                # Normalize the PDF path
                if pdf_path.startswith('/media/'):
                    pdf_path = os.path.join(settings.MEDIA_ROOT, pdf_path.lstrip('/media/'))
                elif not pdf_path.startswith('/'):
                    pdf_path = os.path.join(settings.MEDIA_ROOT, pdf_path)
                
                # Open the PDF and get page count
                pdf_document = fitz.open(pdf_path)
                page_count = len(pdf_document)
                
                # For FirstCry, the label is the last page
                label_page_index = page_count - 1
                pdf_document.close()
            except Exception as e:
                # If we can't determine, default to first page
                print(f"Error determining label page: {e}")
                label_page_index = 0
        
        # Convert file system path to URL if needed
        pdf_url = pdf_path
        if pdf_path.startswith('/') or pdf_path.startswith('C:'):
            # It's a file system path, extract filename
            filename = os.path.basename(pdf_path)
            
            # Determine which directory it belongs to based on platform
            platform_dir_mapping = {
                'AMAZON': 'amazonPdfs',
                'FLIPKART': 'flipkartPdfs',
                'FIRSTCRY': 'firstcryPdfs',
                'MEESHO': 'meeshoPdfs'
            }
            pdf_url = f'/media/{platform_dir_mapping.get(platform_upper, "orderPdfs")}/{filename}'
        
        # Prepare the response
        response_data = {
            'status': 'success',
            'pdf_url': pdf_url,
            'order_number': order.order_number,
            'awb': order.AWB,
            'platform': platform,
            'label_page_index': label_page_index
        }
        
        return JsonResponse(response_data)
    
    except Exception as e:
        print(f"Error in print_invoice: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error processing print request: {str(e)}'
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