"""
Views for handling printing and label-related functionality.
"""
import os
import json
import traceback
from pathlib import Path
from django.utils import timezone
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.core.files import File
from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..models import (
    Picklist, PicklistItem, PicklistItemLocation, UserProfile,
    AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders,
    OrderPDF
)


@require_http_methods(["GET"])
def get_printer_list(request):
    """Return a list of available printers from the system."""
    return JsonResponse({
        'status': 'success',
        'message': 'QZ Tray will detect printers client-side'
    })


@csrf_exempt
@require_http_methods(["POST"])
def save_printer_preferences(request):
    """Save user's printer preferences."""
    try:
        data = json.loads(request.body)
        selected_printer = data.get('printer_name')
        
        if not selected_printer:
            return JsonResponse({
                'status': 'error',
                'message': 'Printer name is required'
            }, status=400)
        
        if request.user.is_authenticated:
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            profile.printer_preference = selected_printer
            profile.save()
            
            return JsonResponse({
                'status': 'success',
                'message': f'Printer preference saved: {selected_printer}'
            })
        else:
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
    """Get pending print jobs for a specific client."""
    client_id = request.GET.get('client_id')
    
    return Response({
        'success': True,
        'pending_jobs': [],
        'client_id': client_id,
        'message': 'No pending print jobs'
    })


@require_http_methods(["GET"])
def get_printer_preferences(request):
    """Get user's saved printer preferences."""
    try:
        preference = None
        
        if request.user.is_authenticated:
            profile = UserProfile.objects.filter(user=request.user).first()
            if profile and profile.printer_preference:
                preference = profile.printer_preference
        
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
    """Send a test print to a specific printer."""
    try:
        data = json.loads(request.body)
        printer_name = data.get('printer_name')
        
        if not printer_name:
            return JsonResponse({
                'status': 'error',
                'message': 'Printer name is required'
            }, status=400)
        
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
    Gets the PDF from file system via OrderPDF model.
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
        
        label_page_index = 0
        if platform_upper == 'FIRSTCRY':
            label_page_index = -1
        
        # Check if PDF exists in OrderPDF model
        pdf_record = OrderPDF.objects.filter(order_id=order_number).first()
        
        if pdf_record and pdf_record.pdf_file:
            # PDF exists - return file URL
            print(f"DEBUG: Using PDF from file system for order {order_number}")
            
            pdf_url = pdf_record.pdf_file.url
            
            return JsonResponse({
                'status': 'success',
                'pdf_url': pdf_url,
                'order_number': order.order_number,
                'awb': getattr(order, 'AWB', 'N/A'),
                'platform': platform,
                'label_page_index': label_page_index,
                'source': 'database'
            })
        
        # PDF not in OrderPDF - check order.pdf_url
        if not order.pdf_url:
            return JsonResponse({
                'status': 'error',
                'message': f'No PDF file found for order {order_number}'
            }, status=404)
        
        pdf_path = order.pdf_url
        
        # If it's a file path, import it to OrderPDF
        if pdf_path.startswith('/') or pdf_path.startswith('C:'):
            if os.path.exists(pdf_path):
                try:
                    filename = os.path.basename(pdf_path)
                    
                    # Create OrderPDF record with file
                    with open(pdf_path, 'rb') as f:
                        pdf_record = OrderPDF.objects.create(
                            order_id=order_number,
                            filename=filename,
                            source_type='file_import'
                        )
                        pdf_record.pdf_file.save(filename, File(f), save=True)
                    
                    print(f"DEBUG: Imported PDF from {pdf_path} to file system")
                    
                    pdf_url = pdf_record.pdf_file.url
                    
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
                    print(f"DEBUG: Error importing PDF: {str(e)}")
                    traceback.print_exc()
            else:
                print(f"DEBUG: PDF file not found at {pdf_path}")
        
        # Fallback to file-based URL
        if pdf_path.startswith('/') or pdf_path.startswith('C:'):
            filename = os.path.basename(pdf_path)
            platform_dir_mapping = {
                'AMAZON': 'amazonPdfs',
                'FLIPKART': 'flipkartPdfs',
                'FIRSTCRY': 'firstcryPdfs',
                'MEESHO': 'meeshoPdfs'
            }
            pdf_url = f"/media/{platform_dir_mapping.get(platform_upper, 'orderPdfs')}/{filename}"
        else:
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
    """Mark an order as printed/processed in the database."""
    try:
        data = json.loads(request.body)
        picklist_id = data.get('picklist_id')
        order_number = data.get('order_number')
        
        if not picklist_id or not order_number:
            return JsonResponse({
                'status': 'error',
                'message': 'Picklist ID and order number are required'
            }, status=400)
        
        print(f"Marking order {order_number} in picklist {picklist_id} as printed")
        
        try:
            picklist = Picklist.objects.get(picklist_id=picklist_id)
        except Picklist.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'Picklist {picklist_id} not found'
            }, status=404)
            
        items = PicklistItem.objects.filter(picklist=picklist, order_number=order_number)
        
        if not items.exists():
            return JsonResponse({
                'status': 'error',
                'message': f'Order {order_number} not found in picklist {picklist_id}'
            }, status=404)
            
        updated_count = 0
        for item in items:
            if not item.picked:
                item.picked = True
                item.save()
                updated_count += 1
                
                location_info, created = PicklistItemLocation.objects.get_or_create(
                    picklist_item=item,
                    defaults={'location': 'Unknown', 'picked': False}
                )
                location_info.picked = True
                location_info.picked_at = timezone.now()
                location_info.save()
        
        platform = picklist.platform.upper() if picklist.platform else "UNKNOWN"
        
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
        
        all_picked = not PicklistItem.objects.filter(picklist=picklist, picked=False).exists()
        
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
    """Mark multiple orders as printed/processed in the database."""
    try:
        data = json.loads(request.body)
        picklist_id = data.get('picklist_id')
        order_numbers = data.get('order_numbers', [])
        
        if not picklist_id or not order_numbers:
            return JsonResponse({
                'status': 'error',
                'message': 'Picklist ID and order numbers are required'
            }, status=400)
        
        print(f"Marking {len(order_numbers)} orders in picklist {picklist_id} as printed")
        
        try:
            picklist = Picklist.objects.get(picklist_id=picklist_id)
        except Picklist.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'Picklist {picklist_id} not found'
            }, status=404)
        
        platform = picklist.platform.upper() if picklist.platform else "UNKNOWN"
        
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        total_updated_items = 0
        total_updated_orders = 0
        platform_orders_updated = 0
        processed_orders = []
        
        for order_number in order_numbers:
            items = PicklistItem.objects.filter(picklist=picklist, order_number=order_number)
            
            if not items.exists():
                print(f"Order {order_number} not found in picklist {picklist_id}")
                continue
            
            order_updated_items = 0
            for item in items:
                if not item.picked:
                    item.picked = True
                    item.save()
                    order_updated_items += 1
                    
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
            
            if order_updated_items > 0:
                total_updated_items += order_updated_items
                total_updated_orders += 1
                processed_orders.append(order_number)
                print(f"Order {order_number}: {order_updated_items} items marked as picked")
            
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
        
        all_picked = not PicklistItem.objects.filter(picklist=picklist, picked=False).exists()
        
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
    """Save the AWB number for an order across all applicable tables."""
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
            
        print(f"Saving AWB {awb} for order {order_number} from picklist {picklist_id}")
        
        platform = None
        updated = 0
        
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        for plat, model in model_mapping.items():
            if model.objects.filter(order_number=order_number).exists():
                platform = plat
                updated = model.objects.filter(order_number=order_number).update(AWB=awb)
                break
                
        if not platform:
            return JsonResponse({
                'status': 'error',
                'message': f'Order {order_number} not found in any platform'
            }, status=404)
            
        picklist_items_updated = 0
        if picklist_id:
            try:
                picklist = Picklist.objects.get(picklist_id=picklist_id)
                items = PicklistItem.objects.filter(picklist=picklist, order_number=order_number)
                
                if hasattr(PicklistItem, 'awb'):
                    for item in items:
                        item.awb = awb
                        item.save()
                        picklist_items_updated += 1
                        
            except Picklist.DoesNotExist:
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
    Gets the PDF from file system via OrderPDF model.
    """
    try:
        data = json.loads(request.body)
        platform = data.get('platform')
        order_number = data.get('order_number')
        awb = data.get('awb')
        
        if not platform or not (order_number or awb):
            return JsonResponse({
                'status': 'error',
                'message': 'Platform and either order number or AWB are required'
            }, status=400)
        
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
            
        order_number = order.order_number
        
        label_page_index = 0
        if platform_upper == 'FIRSTCRY':
            label_page_index = -1
        
        # Check if PDF exists in OrderPDF model
        pdf_record = OrderPDF.objects.filter(order_id=order_number).first()
        
        if pdf_record and pdf_record.pdf_file:
            print(f"DEBUG: Using PDF from file system for invoice {order_number}")
            
            pdf_url = pdf_record.pdf_file.url
            
            return JsonResponse({
                'status': 'success',
                'pdf_url': pdf_url,
                'order_number': order.order_number,
                'awb': getattr(order, 'AWB', 'N/A'),
                'platform': platform,
                'label_page_index': label_page_index,
                'source': 'database'
            })
        
        # PDF not in OrderPDF - check order.pdf_url
        if not order.pdf_url:
            return JsonResponse({
                'status': 'error',
                'message': f'No PDF file found for order {order_number}'
            }, status=404)
        
        pdf_path = order.pdf_url
        
        # If it's a file path, import it to OrderPDF
        if pdf_path.startswith('/') or pdf_path.startswith('C:'):
            if os.path.exists(pdf_path):
                try:
                    filename = os.path.basename(pdf_path)
                    
                    with open(pdf_path, 'rb') as f:
                        pdf_record = OrderPDF.objects.create(
                            order_id=order_number,
                            filename=filename,
                            source_type='file_import'
                        )
                        pdf_record.pdf_file.save(filename, File(f), save=True)
                    
                    print(f"DEBUG: Imported PDF from {pdf_path} to file system")
                    
                    pdf_url = pdf_record.pdf_file.url
                    
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
                    print(f"DEBUG: Error importing PDF: {str(e)}")
                    traceback.print_exc()
            else:
                print(f"DEBUG: PDF file not found at {pdf_path}")
        
        # Fallback to file-based URL
        if pdf_path.startswith('/') or pdf_path.startswith('C:'):
            filename = os.path.basename(pdf_path)
            platform_dir_mapping = {
                'AMAZON': 'amazonPdfs',
                'FLIPKART': 'flipkartPdfs',
                'FIRSTCRY': 'firstcryPdfs',
                'MEESHO': 'meeshoPdfs'
            }
            pdf_url = f"/media/{platform_dir_mapping.get(platform_upper, 'orderPdfs')}/{filename}"
        else:
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
    Stream PDF content from file system.
    """
    try:
        pdf_record = OrderPDF.objects.filter(order_id=order_id).first()
        
        if not pdf_record or not pdf_record.pdf_file:
            return JsonResponse({
                'status': 'error',
                'message': f'PDF for order {order_id} not found'
            }, status=404)
        
        # Get file path
        file_path = pdf_record.pdf_file.path
        
        if not os.path.exists(file_path):
            return JsonResponse({
                'status': 'error',
                'message': f'PDF file not found on disk'
            }, status=404)
        
        filename = pdf_record.filename or f"order_{order_id}.pdf"
        
        # Stream file from disk
        with open(file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            
            # Add CORS headers
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
    """Search for an order by AWB number."""
    awb = request.GET.get('awb', '').strip()
    
    if not awb:
        return JsonResponse({
            'status': 'error',
            'message': 'AWB number is required'
        }, status=400)
    
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