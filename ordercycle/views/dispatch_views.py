import csv
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.db.models import Count, Case, When, IntegerField, F, Q
from django.utils import timezone
import json, os
import traceback
from django.views.decorators.http import require_POST
from ordercycle.models import Picklist, PicklistItem, AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders, PicklistDispatchStatus
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime
from django.db import transaction



def get_dispatch_picklists(request):
    """
    Get picklists with status 'Dispatch' - Simple and direct approach
    """
    try:
        # Get platform filter from query parameters
        platform_filter = request.GET.get('platform', '').upper()
        
        # Get date filters
        specific_date = request.GET.get('date')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        print(f"Date filters - specific: {specific_date}, start: {start_date}, end: {end_date}")
        print(f"Platform filter: {platform_filter}")
        
        # Simple query: Get picklists with status 'Dispatch'
        picklists_query = Picklist.objects.filter(status='DISPATCH').order_by('-created_at')
        
        # Apply date filtering if provided
        if specific_date:
            try:
                filter_date = datetime.strptime(specific_date, '%Y-%m-%d').date()
                picklists_query = picklists_query.filter(created_at__date=filter_date)
                print(f"Applied specific date filter: {filter_date}")
            except ValueError as e:
                print(f"Invalid specific date format: {specific_date}, error: {e}")
                
        elif start_date and end_date:
            try:
                start_filter_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_filter_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                # Validate date range
                if start_filter_date > end_filter_date:
                    raise ValueError("Start date cannot be later than end date")
                
                # Check if range is not too large (90 days max)
                date_diff = (end_filter_date - start_filter_date).days
                if date_diff > 90:
                    raise ValueError("Date range cannot exceed 90 days")
                
                picklists_query = picklists_query.filter(
                    created_at__date__gte=start_filter_date,
                    created_at__date__lte=end_filter_date
                )
                print(f"Applied date range filter: {start_filter_date} to {end_filter_date}")
                
            except ValueError as e:
                print(f"Invalid date range: {start_date} to {end_date}, error: {e}")
        
        # Apply platform filter if specified
        if platform_filter and platform_filter != 'ALL':
            picklists_query = picklists_query.filter(platform__iexact=platform_filter)
            print(f"Applied platform filter: {platform_filter}")
        
        picklists = picklists_query
        picklists_data = []
        
        print(f"Found {picklists.count()} picklists with status 'Dispatch'")
        
        # Process each picklist to get order counts
        for picklist in picklists:
            try:
                # Get all items in this picklist
                picklist_items = PicklistItem.objects.filter(picklist=picklist)
                total_unique_orders = picklist_items.values('order_number').distinct().count()
                
                if total_unique_orders == 0:
                    continue
                
                platform = picklist.platform.upper()
                order_numbers = list(picklist_items.values_list('order_number', flat=True).distinct())
                
                dispatched_orders = 0
                complete_orders = 0
                
                # Count order statuses
                for order_number in order_numbers:
                    try:
                        order = None
                        
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
                        
                        if order:
                            if order.status == 'Dispatch':
                                dispatched_orders += 1
                            elif order.status == 'Complete':
                                complete_orders += 1
                                
                    except Exception as e:
                        print(f"Error processing order {order_number}: {e}")
                        continue
                
                # Calculate dispatch percentage
                dispatch_percentage = 0
                if total_unique_orders > 0:
                    dispatch_percentage = round((dispatched_orders / total_unique_orders) * 100, 1)
                
                # Add to results - show ALL picklists with status 'Dispatch'
                picklists_data.append({
                    'picklist_id': picklist.picklist_id,
                    'picklist_type': picklist.picklist_type or 'N/A',
                    'platform': picklist.platform,
                    'total_orders': total_unique_orders,
                    'dispatch_orders': dispatched_orders,
                    'complete_orders': complete_orders,
                    'total_relevant_orders': dispatched_orders + complete_orders,
                    'dispatch_percentage': dispatch_percentage,
                    'status': picklist.status,
                    'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'created_date': picklist.created_at.strftime('%Y-%m-%d')
                })
                
                print(f"Added picklist {picklist.picklist_id}: {dispatched_orders} dispatched, {complete_orders} complete, {dispatch_percentage}% dispatch rate")
                
            except Exception as e:
                print(f"Error processing picklist {picklist.picklist_id}: {e}")
                continue
        
        # Sort by dispatch percentage (descending), then by total orders
        picklists_data.sort(key=lambda x: (x['dispatch_percentage'], x['total_orders']), reverse=True)
        
        # Prepare response with date filter info
        date_filter_info = {}
        if specific_date:
            date_filter_info = {
                'filter_type': 'specific',
                'date': specific_date,
                'display_text': f"Data for {specific_date}"
            }
        elif start_date and end_date:
            date_filter_info = {
                'filter_type': 'range',
                'start_date': start_date,
                'end_date': end_date,
                'display_text': f"Data from {start_date} to {end_date}"
            }
        else:
            date_filter_info = {
                'filter_type': 'all',
                'display_text': f"All dispatch picklists"
            }
        
        print(f"Returning {len(picklists_data)} dispatch picklists")
        
        return JsonResponse({
            'status': 'success',
            'picklists': picklists_data,
            'using_dispatch_model': False,
            'filtered_platform': platform_filter or 'ALL',
            'date_filter': date_filter_info,
            'total_picklists': len(picklists_data)
        })
    
    except Exception as e:
        print(f"Error in get_dispatch_picklists: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return JsonResponse({
            'status': 'error',
            'message': f'Error retrieving dispatch picklists: {str(e)}',
            'picklists': [],
            'date_filter': {
                'filter_type': 'error',
                'date': timezone.now().date().strftime('%Y-%m-%d'),
                'display_text': 'Error loading data'
            }
        })
# ===== ENHANCED GET_DISPATCH_ORDERS WITH DATE CONTEXT =====
def get_dispatch_orders(request, picklist_id):
    """
    Get Complete and Dispatch orders for a specific picklist
    Enhanced with date context for better filtering and display
    """
    try:
        picklist = get_object_or_404(Picklist, picklist_id=picklist_id)
        
        # Get date filters for context
        specific_date = request.GET.get('date')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        print(f"Getting dispatch orders for picklist {picklist_id} with date context")
        
        picklist_items = PicklistItem.objects.filter(picklist=picklist)
        
        total_orders = picklist_items.values('order_number').distinct().count()
        dispatch_orders = 0
        complete_orders = 0
        orders_data = []
        
        platform = picklist.platform.upper()
        order_numbers = picklist_items.values_list('order_number', flat=True).distinct()
        
        for order_number in order_numbers:
            try:
                # Get the order based on platform
                orders = None
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
                
                if not orders or not orders.exists():
                    continue
                
                order = orders.first()
                
                # Count Complete and Dispatch orders
                is_dispatch = order.status == 'Dispatch'
                is_complete = order.status == 'Complete'
                
                if is_dispatch:
                    dispatch_orders += 1
                elif is_complete:
                    complete_orders += 1
                
                # Only include Complete or Dispatch orders in the response
                if is_dispatch or is_complete:
                    # Find the associated picklist items
                    items = picklist_items.filter(order_number=order_number)
                    
                    # Add each item as a separate entry in orders_data
                    for item in items:
                        orders_data.append({
                            'order_number': order.order_number,
                            'sku': item.sku,
                            'quantity': item.quantity,
                            'status': order.status,
                            'awb': getattr(order, 'AWB', None) or 'N/A',
                            'sort_priority': 1 if is_dispatch else 2  # Dispatch first, then Complete
                        })
                        
            except Exception as e:
                print(f"Error processing order {order_number}: {e}")
                continue
        
        # Sort orders - Dispatch first, then Complete
        orders_data.sort(key=lambda x: x['sort_priority'])
        
        # Remove the temporary sorting field
        for order in orders_data:
            order.pop('sort_priority', None)
        
        # Calculate dispatch percentage
        dispatch_percentage = 0
        if total_orders > 0:
            dispatch_percentage = round((dispatch_orders / total_orders) * 100)
        
        # Prepare date context information
        date_context = {
            'picklist_date': picklist.created_at.strftime('%Y-%m-%d'),
            'picklist_created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'filter_date': specific_date,
            'filter_start': start_date,
            'filter_end': end_date
        }
        
        # Determine if picklist matches current date filter
        picklist_date = picklist.created_at.date()
        matches_filter = False
        
        if specific_date:
            try:
                filter_date = datetime.strptime(specific_date, '%Y-%m-%d').date()
                matches_filter = picklist_date == filter_date
            except ValueError:
                matches_filter = False
        elif start_date and end_date:
            try:
                start_filter_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_filter_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                matches_filter = start_filter_date <= picklist_date <= end_filter_date
            except ValueError:
                matches_filter = False
        else:
            # Default to today
            matches_filter = picklist_date == timezone.now().date()
        
        date_context['matches_current_filter'] = matches_filter
        
        response_data = {
            'picklist_id': picklist.picklist_id,
            'platform': picklist.platform,
            'total_orders': total_orders,
            'dispatch_orders': dispatch_orders,
            'complete_orders': complete_orders,
            'total_relevant_orders': dispatch_orders + complete_orders,
            'dispatch_percentage': dispatch_percentage,
            'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'created_date': picklist.created_at.strftime('%Y-%m-%d'),
            'orders': orders_data,
            'date_context': date_context
        }
        
        return JsonResponse(response_data)
    
    except Exception as e:
        print(f"Error in get_dispatch_orders: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return JsonResponse({
            'status': 'error',
            'message': f'Error retrieving dispatch orders: {str(e)}',
            'date_context': {
                'filter_date': specific_date,
                'filter_start': start_date,
                'filter_end': end_date,
                'error': str(e)
            }
        }, status=500)

# ===== NEW ENDPOINT FOR DATE-BASED ANALYTICS =====
def get_dispatch_analytics_by_date(request):
    """
    Get dispatch analytics aggregated by date range
    Useful for generating reports and trends
    """
    try:
        # Get date filters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        platform_filter = request.GET.get('platform', '').upper()
        group_by = request.GET.get('group_by', 'date')  # 'date', 'platform', 'week', 'month'
        
        if not start_date or not end_date:
            return JsonResponse({
                'status': 'error',
                'message': 'start_date and end_date parameters are required'
            }, status=400)
        
        try:
            start_filter_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_filter_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # Validate date range
            if start_filter_date > end_filter_date:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Start date cannot be later than end date'
                }, status=400)
            
            # Check if range is not too large (90 days max for detailed analytics)
            date_diff = (end_filter_date - start_filter_date).days
            if date_diff > 90:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Date range cannot exceed 90 days for detailed analytics'
                }, status=400)
                
        except ValueError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid date format. Use YYYY-MM-DD'
            }, status=400)
        
        # Get picklists in date range
        picklists_query = Picklist.objects.filter(
            created_at__date__gte=start_filter_date,
            created_at__date__lte=end_filter_date
        ).order_by('created_at')
        
        if platform_filter and platform_filter != 'ALL':
            picklists_query = picklists_query.filter(platform__iexact=platform_filter)
        
        # Group analytics by specified grouping
        analytics_data = {}
        
        for picklist in picklists_query:
            try:
                # Determine grouping key
                if group_by == 'date':
                    group_key = picklist.created_at.date().strftime('%Y-%m-%d')
                    display_key = picklist.created_at.date().strftime('%Y-%m-%d')
                elif group_by == 'week':
                    # Get Monday of the week
                    monday = picklist.created_at.date() - timedelta(days=picklist.created_at.weekday())
                    group_key = monday.strftime('%Y-%m-%d')
                    display_key = f"Week of {monday.strftime('%Y-%m-%d')}"
                elif group_by == 'month':
                    group_key = picklist.created_at.date().strftime('%Y-%m')
                    display_key = picklist.created_at.date().strftime('%B %Y')
                elif group_by == 'platform':
                    group_key = picklist.platform.upper()
                    display_key = picklist.platform.upper()
                else:
                    group_key = picklist.created_at.date().strftime('%Y-%m-%d')
                    display_key = picklist.created_at.date().strftime('%Y-%m-%d')
                
                if group_key not in analytics_data:
                    analytics_data[group_key] = {
                        'group_key': group_key,
                        'display_key': display_key,
                        'total_picklists': 0,
                        'total_orders': 0,
                        'dispatched_orders': 0,
                        'complete_orders': 0,
                        'platforms': set(),
                        'picklist_details': []
                    }
                
                # Calculate orders for this picklist
                picklist_items = PicklistItem.objects.filter(picklist=picklist)
                total_orders = picklist_items.values('order_number').distinct().count()
                
                if total_orders > 0:
                    platform = picklist.platform.upper()
                    order_numbers = list(picklist_items.values_list('order_number', flat=True).distinct())
                    
                    dispatched_count = 0
                    complete_count = 0
                    
                    for order_number in order_numbers:
                        try:
                            order = None
                            if platform == 'AMAZON':
                                order = AmazonOrders.objects.filter(order_number=order_number).first()
                            elif platform == 'FLIPKART':
                                order = FlipkarOrders.objects.filter(order_number=order_number).first()
                            elif platform == 'FIRSTCRY':
                                order = FirstcryOrders.objects.filter(order_number=order_number).first()
                            elif platform == 'MEESHO':
                                order = MeeshoOrders.objects.filter(order_number=order_number).first()
                            
                            if order:
                                if order.status == 'Dispatch':
                                    dispatched_count += 1
                                elif order.status == 'Complete':
                                    complete_count += 1
                                    
                        except Exception as e:
                            print(f"Error processing order {order_number} in analytics: {e}")
                            continue
                    
                    # Update analytics data
                    analytics_data[group_key]['total_picklists'] += 1
                    analytics_data[group_key]['total_orders'] += total_orders
                    analytics_data[group_key]['dispatched_orders'] += dispatched_count
                    analytics_data[group_key]['complete_orders'] += complete_count
                    analytics_data[group_key]['platforms'].add(picklist.platform)
                    
                    # Add picklist details
                    dispatch_percentage = 0
                    if total_orders > 0:
                        dispatch_percentage = round((dispatched_count / total_orders) * 100, 1)
                    
                    analytics_data[group_key]['picklist_details'].append({
                        'picklist_id': picklist.picklist_id,
                        'platform': picklist.platform,
                        'total_orders': total_orders,
                        'dispatched_orders': dispatched_count,
                        'complete_orders': complete_count,
                        'dispatch_percentage': dispatch_percentage,
                        'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
            except Exception as e:
                print(f"Error processing picklist {picklist.picklist_id} in analytics: {e}")
                continue
        
        # Convert to list and calculate percentages
        analytics_list = []
        for group_data in analytics_data.values():
            total_orders = group_data['total_orders']
            dispatch_percentage = 0
            complete_percentage = 0
            
            if total_orders > 0:
                dispatch_percentage = round((group_data['dispatched_orders'] / total_orders) * 100, 1)
                complete_percentage = round((group_data['complete_orders'] / total_orders) * 100, 1)
            
            analytics_list.append({
                'group_key': group_data['group_key'],
                'display_key': group_data['display_key'],
                'total_picklists': group_data['total_picklists'],
                'total_orders': total_orders,
                'dispatched_orders': group_data['dispatched_orders'],
                'complete_orders': group_data['complete_orders'],
                'dispatch_percentage': dispatch_percentage,
                'complete_percentage': complete_percentage,
                'platforms': list(group_data['platforms']),
                'picklist_details': group_data['picklist_details']
            })
        
        # Sort by group key
        analytics_list.sort(key=lambda x: x['group_key'])
        
        # Calculate summary totals
        summary = {
            'total_picklists': sum(d['total_picklists'] for d in analytics_list),
            'total_orders': sum(d['total_orders'] for d in analytics_list),
            'total_dispatched': sum(d['dispatched_orders'] for d in analytics_list),
            'total_complete': sum(d['complete_orders'] for d in analytics_list),
            'overall_dispatch_percentage': 0,
            'overall_complete_percentage': 0,
            'date_range_days': date_diff + 1
        }
        
        if summary['total_orders'] > 0:
            summary['overall_dispatch_percentage'] = round(
                (summary['total_dispatched'] / summary['total_orders']) * 100, 1
            )
            summary['overall_complete_percentage'] = round(
                (summary['total_complete'] / summary['total_orders']) * 100, 1
            )
        
        return JsonResponse({
            'status': 'success',
            'date_range': {
                'start_date': start_date,
                'end_date': end_date,
                'platform_filter': platform_filter or 'ALL',
                'group_by': group_by
            },
            'analytics': analytics_list,
            'summary': summary
        })
        
    except Exception as e:
        print(f"Error in get_dispatch_analytics_by_date: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return JsonResponse({
            'status': 'error',
            'message': f'Error retrieving analytics: {str(e)}'
        }, status=500)


# Mark orders as dispatched (now completed)
def mark_orders_as_dispatched(request, picklist_id):
    """
    Enhanced version of mark orders as dispatched with date tracking
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    picklist = get_object_or_404(Picklist, picklist_id=picklist_id)
    platform = picklist.platform.upper()
    
    try:
        data = json.loads(request.body)
        order_numbers = data.get('order_numbers', [])
        
        if not order_numbers:
            return JsonResponse({'error': 'No orders provided'}, status=400)
        
        # Track the dispatch date for analytics
        dispatch_date = timezone.now()
        
        # Update order status based on platform
        updated_count = 0
        updated_orders = []
        
        for order_number in order_numbers:
            try:
                orders = None
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
                
                if orders and orders.exists():
                    # Update orders and track changes
                    for order in orders:
                        if order.status == 'Complete':  # Only update Complete orders
                            order.status = 'Dispatch'
                            order.save()
                            updated_orders.append({
                                'order_number': order_number,
                                'platform': platform,
                                'dispatched_at': dispatch_date.strftime('%Y-%m-%d %H:%M:%S')
                            })
                    updated_count += 1
                    
            except Exception as e:
                print(f"Error updating order {order_number}: {e}")
                continue
        
        # Update dispatch status tracking
        try:
            dispatch_status, created = PicklistDispatchStatus.objects.get_or_create(
                picklist=picklist,
                defaults={
                    'total_orders': 0,
                    'dispatched_orders': 0,
                    'complete_orders': 0,
                    'is_fully_dispatched': False
                }
            )
            
            # Update the status
            all_dispatched = dispatch_status.update_status_with_complete_and_dispatch()
            
            # Include dispatch status info in the response
            dispatch_info = {
                'total_orders': dispatch_status.total_orders,
                'dispatched_orders': dispatch_status.dispatched_orders,
                'complete_orders': dispatch_status.complete_orders,
                'percentage': round((dispatch_status.dispatched_orders / dispatch_status.total_orders * 100), 1) if dispatch_status.total_orders > 0 else 0,
                'is_fully_dispatched': dispatch_status.is_fully_dispatched
            }
            
        except Exception as e:
            print(f"Error updating dispatch status: {str(e)}")
            dispatch_info = None
            all_dispatched = False
        
        response_data = {
            'success': True,
            'message': f'Successfully marked {updated_count} order(s) as dispatched.',
            'updated_count': updated_count,
            'all_dispatched': all_dispatched,
            'dispatch_date': dispatch_date.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_orders': updated_orders
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
    Search orders by AWB number - looks for Complete orders that can be dispatched
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

def get_date_range_statistics(request):
    """
    Get comprehensive statistics for a date range
    """
    try:
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date', start_date)  # Default to same date if not provided
        platform_filter = request.GET.get('platform', '').upper()
        
        if not start_date:
            return JsonResponse({
                'status': 'error',
                'message': 'start_date parameter is required'
            }, status=400)
        
        try:
            start_filter_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_filter_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid date format. Use YYYY-MM-DD'
            }, status=400)
        
        # Get picklists in date range
        picklists_query = Picklist.objects.filter(
            created_at__date__gte=start_filter_date,
            created_at__date__lte=end_filter_date
        )
        
        if platform_filter and platform_filter != 'ALL':
            picklists_query = picklists_query.filter(platform__iexact=platform_filter)
        
        # Initialize statistics
        stats = {
            'date_range': {
                'start': start_date,
                'end': end_date,
                'days': (end_filter_date - start_filter_date).days + 1
            },
            'platform': platform_filter or 'ALL',
            'totals': {
                'picklists': 0,
                'orders': 0,
                'dispatched': 0,
                'complete': 0,
                'other_status': 0
            },
            'by_platform': {},
            'by_date': {},
            'by_status': {
                'Dispatch': 0,
                'Complete': 0,
                'Pack': 0,
                'Pick': 0,
                'Ready to Process': 0,
                'Other': 0
            }
        }
        
        # Process each picklist
        for picklist in picklists_query:
            try:
                platform = picklist.platform.upper()
                picklist_date = picklist.created_at.date().strftime('%Y-%m-%d')
                
                # Initialize platform stats if needed
                if platform not in stats['by_platform']:
                    stats['by_platform'][platform] = {
                        'picklists': 0,
                        'orders': 0,
                        'dispatched': 0,
                        'complete': 0
                    }
                
                # Initialize date stats if needed
                if picklist_date not in stats['by_date']:
                    stats['by_date'][picklist_date] = {
                        'picklists': 0,
                        'orders': 0,
                        'dispatched': 0,
                        'complete': 0
                    }
                
                # Get picklist items and orders
                picklist_items = PicklistItem.objects.filter(picklist=picklist)
                total_orders = picklist_items.values('order_number').distinct().count()
                order_numbers = list(picklist_items.values_list('order_number', flat=True).distinct())
                
                dispatched_count = 0
                complete_count = 0
                
                # Check order statuses
                for order_number in order_numbers:
                    try:
                        order = None
                        if platform == 'AMAZON':
                            order = AmazonOrders.objects.filter(order_number=order_number).first()
                        elif platform == 'FLIPKART':
                            order = FlipkarOrders.objects.filter(order_number=order_number).first()
                        elif platform == 'FIRSTCRY':
                            order = FirstcryOrders.objects.filter(order_number=order_number).first()
                        elif platform == 'MEESHO':
                            order = MeeshoOrders.objects.filter(order_number=order_number).first()
                        
                        if order:
                            if order.status == 'Dispatch':
                                dispatched_count += 1
                            elif order.status == 'Complete':
                                complete_count += 1
                            
                            # Update status statistics
                            if order.status in stats['by_status']:
                                stats['by_status'][order.status] += 1
                            else:
                                stats['by_status']['Other'] += 1
                                
                    except Exception as e:
                        print(f"Error processing order {order_number} in statistics: {e}")
                        continue
                
                # Update statistics
                stats['totals']['picklists'] += 1
                stats['totals']['orders'] += total_orders
                stats['totals']['dispatched'] += dispatched_count
                stats['totals']['complete'] += complete_count
                
                stats['by_platform'][platform]['picklists'] += 1
                stats['by_platform'][platform]['orders'] += total_orders
                stats['by_platform'][platform]['dispatched'] += dispatched_count
                stats['by_platform'][platform]['complete'] += complete_count
                
                stats['by_date'][picklist_date]['picklists'] += 1
                stats['by_date'][picklist_date]['orders'] += total_orders
                stats['by_date'][picklist_date]['dispatched'] += dispatched_count
                stats['by_date'][picklist_date]['complete'] += complete_count
                
            except Exception as e:
                print(f"Error processing picklist {picklist.picklist_id} in statistics: {e}")
                continue
        
        # Calculate percentages
        if stats['totals']['orders'] > 0:
            stats['percentages'] = {
                'dispatch': round((stats['totals']['dispatched'] / stats['totals']['orders']) * 100, 1),
                'complete': round((stats['totals']['complete'] / stats['totals']['orders']) * 100, 1)
            }
        else:
            stats['percentages'] = {'dispatch': 0, 'complete': 0}
        
        return JsonResponse({
            'status': 'success',
            'statistics': stats
        })
        
    except Exception as e:
        print(f"Error in get_date_range_statistics: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return JsonResponse({
            'status': 'error',
            'message': f'Error retrieving statistics: {str(e)}'
        }, status=500)


@csrf_exempt
@require_POST
def bulk_change_to_dispatch(request):
    """
    Change multiple orders' status from Complete to Dispatch with enhanced date tracking
    """
    try:
        data = json.loads(request.body)
        orders = data.get('orders', [])
        awb = data.get('awb')
        
        if not orders:
            return JsonResponse({
                'error': 'No orders provided'
            }, status=400)
        
        # Track changes with timestamps
        updated_count = 0
        deleted_files = 0
        failed_orders = []
        affected_picklists = set()
        dispatch_timestamp = timezone.now()
        updated_orders_log = []
        
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
            
            try:
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
                
                # Filter for Complete status orders
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
                        except Exception as e:
                            print(f"Error deleting PDF file {pdf_path}: {str(e)}")
                    
                    # Clear the pdf_path field after deleting the file
                    if hasattr(order, 'pdf_path'):
                        order.pdf_path = ''
                        order.save()
                
                # Update to Dispatch
                count = complete_orders.update(status='Dispatch')
                updated_count += count
                
                # Log the change
                updated_orders_log.append({
                    'order_number': order_number,
                    'platform': platform.upper(),
                    'awb': awb,
                    'dispatched_at': dispatch_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'orders_affected': count
                })
                
                # Find which picklists contain this order to update dispatch status
                try:
                    picklist_items = PicklistItem.objects.filter(order_number=order_number)
                    for item in picklist_items:
                        affected_picklists.add(item.picklist.picklist_id)
                except Exception as e:
                    print(f"Error finding picklists for order {order_number}: {str(e)}")
                    
            except Exception as e:
                failed_orders.append({
                    'order_number': order_number,
                    'platform': platform,
                    'reason': f'Processing error: {str(e)}'
                })
                continue
        
        # Update dispatch status for all affected picklists
        updated_picklists = []
        for picklist_id in affected_picklists:
            try:
                picklist = Picklist.objects.get(picklist_id=picklist_id)
                
                # Get or create dispatch status
                dispatch_status, created = PicklistDispatchStatus.objects.get_or_create(
                    picklist=picklist,
                    defaults={
                        'total_orders': 0,
                        'dispatched_orders': 0,
                        'complete_orders': 0,
                        'is_fully_dispatched': False
                    }
                )
                
                # Update the dispatch status
                was_fully_dispatched = dispatch_status.update_status_with_complete_and_dispatch()
                updated_picklists.append({
                    'picklist_id': picklist_id,
                    'picklist_date': picklist.created_at.strftime('%Y-%m-%d'),
                    'total_orders': dispatch_status.total_orders,
                    'dispatched_orders': dispatch_status.dispatched_orders,
                    'complete_orders': dispatch_status.complete_orders,
                    'is_fully_dispatched': was_fully_dispatched,
                    'percentage': round((dispatch_status.dispatched_orders / dispatch_status.total_orders * 100), 1) if dispatch_status.total_orders > 0 else 0
                })
                
            except Exception as e:
                print(f"Error updating dispatch status for picklist {picklist_id}: {str(e)}")
        
        return JsonResponse({
            'message': f'Successfully changed {updated_count} order(s) from Complete to Dispatch status',
            'updated_count': updated_count,
            'deleted_files': deleted_files,
            'failed_orders': failed_orders,
            'updated_picklists': updated_picklists,
            'affected_picklists_count': len(affected_picklists),
            'dispatch_timestamp': dispatch_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_orders_log': updated_orders_log
        })
    
    except Exception as e:
        print(f"Error in bulk_change_to_dispatch: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'error': str(e)
        }, status=500)

def download_dispatch_csv_and_cleanup(request, picklist_id):
    """
    Download CSV report for fully dispatched picklist with enhanced date information
    """
    try:
        picklist = get_object_or_404(Picklist, picklist_id=picklist_id)
        
        # Verify that the picklist is fully dispatched
        picklist_items = PicklistItem.objects.filter(picklist=picklist)
        total_unique_orders = picklist_items.values('order_number').distinct().count()
        
        if total_unique_orders == 0:
            return JsonResponse({
                'error': 'No orders found in this picklist'
            }, status=400)
        
        platform = picklist.platform.upper()
        order_numbers = list(picklist_items.values_list('order_number', flat=True).distinct())
        
        # Count dispatched orders and collect all order data
        dispatched_orders = 0
        orders_data = []
        all_order_records = []
        
        for order_number in order_numbers:
            try:
                order_records = []
                is_order_dispatched = False
                
                # Get ALL records for this order number
                if platform == 'AMAZON':
                    order_records = list(AmazonOrders.objects.filter(order_number=order_number))
                elif platform == 'FLIPKART':
                    order_records = list(FlipkarOrders.objects.filter(order_number=order_number))
                elif platform == 'FIRSTCRY':
                    order_records = list(FirstcryOrders.objects.filter(order_number=order_number))
                elif platform == 'MEESHO':
                    order_records = list(MeeshoOrders.objects.filter(order_number=order_number))
                
                if order_records:
                    # Check if ALL records for this order are in Dispatch status
                    all_dispatched = all(record.status == 'Dispatch' for record in order_records)
                    
                    if all_dispatched:
                        dispatched_orders += 1
                        is_order_dispatched = True
                    
                    # Add all records to the reference list
                    all_order_records.extend(order_records)
                    
                    # Add order data to CSV if dispatched
                    if is_order_dispatched:
                        order_items = picklist_items.filter(order_number=order_number)
                        
                        for item in order_items:
                            # Find the order record that matches this SKU
                            matching_record = None
                            for record in order_records:
                                if record.sku == item.sku:
                                    matching_record = record
                                    break
                            
                            if matching_record:
                                orders_data.append({
                                    'order_number': matching_record.order_number,
                                    'sku': item.sku,
                                    'quantity': item.quantity,
                                    'platform': platform,
                                    'status': matching_record.status,
                                    'awb': getattr(matching_record, 'AWB', ''),
                                    'order_type': getattr(matching_record, 'order_type', ''),
                                    'pdf_url': getattr(matching_record, 'pdf_url', '')
                                })
                                
            except Exception as e:
                print(f"Error processing order {order_number} for CSV: {e}")
                continue
        
        # Check if all orders are dispatched
        if dispatched_orders != total_unique_orders:
            return JsonResponse({
                'error': f'Cannot download CSV. Only {dispatched_orders} out of {total_unique_orders} orders are fully dispatched.',
                'dispatched_orders': dispatched_orders,
                'total_orders': total_unique_orders,
                'total_records_found': len(all_order_records)
            }, status=400)
        
        # Create CSV response with enhanced headers
        response = HttpResponse(content_type='text/csv')
        
        # Enhanced filename with date information
        export_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        picklist_date = picklist.created_at.strftime("%Y%m%d")
        filename = f'dispatch_report_{picklist_id}_{picklist_date}_{export_timestamp}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Enhanced CSV headers with date information
        writer.writerow([
            'Picklist ID',
            'Picklist Date',
            'Order Number', 
            'SKU', 
            'Quantity', 
            'Platform', 
            'Status', 
            'AWB', 
            'Order Type',
            'PDF URL',
            'Export Date',
            'Export Time'
        ])
        
        # Write data rows with enhanced date information
        export_date = datetime.now().strftime('%Y-%m-%d')
        export_time = datetime.now().strftime('%H:%M:%S')
        picklist_created_date = picklist.created_at.strftime('%Y-%m-%d')
        
        for order in orders_data:
            writer.writerow([
                picklist_id,
                picklist_created_date,
                order['order_number'],
                order['sku'],
                order['quantity'],
                order['platform'],
                order['status'],
                order['awb'],
                order['order_type'],
                order['pdf_url'],
                export_date,
                export_time
            ])
        
        # Log the CSV generation with date context
        print(f"CSV report generated for picklist {picklist_id}:")
        print(f"- Picklist created: {picklist_created_date}")
        print(f"- Total unique orders: {total_unique_orders}")
        print(f"- Total order records: {len(all_order_records)}")
        print(f"- Export timestamp: {export_timestamp}")
        print(f"- All data preserved in database")
        
        return response
        
    except Exception as e:
        print(f"Error in download_dispatch_csv_and_cleanup: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'error': f'Error generating CSV report: {str(e)}'
        }, status=500)

def check_picklist_fully_dispatched(request, picklist_id):
    """
    Check if a picklist is fully dispatched (all orders in Dispatch status)
    """
    try:
        picklist = get_object_or_404(Picklist, picklist_id=picklist_id)
        
        # Try to get from PicklistDispatchStatus first
        try:
            dispatch_status = PicklistDispatchStatus.objects.get(picklist=picklist)
            # ✅ FIX: Use the enhanced method that checks both Complete and Dispatch
            dispatch_status.update_status_with_complete_and_dispatch()
            
            return JsonResponse({
                'fully_dispatched': dispatch_status.is_fully_dispatched,
                'dispatched_orders': dispatch_status.dispatched_orders,
                'total_orders': dispatch_status.total_orders,
                'complete_orders': getattr(dispatch_status, 'complete_orders', 0),  # Add this
                'percentage': round((dispatch_status.dispatched_orders / dispatch_status.total_orders * 100), 1) if dispatch_status.total_orders > 0 else 0
            })
            
        except PicklistDispatchStatus.DoesNotExist:
            # Fall back to direct checking - also needs to be fixed
            picklist_items = PicklistItem.objects.filter(picklist=picklist)
            total_orders = picklist_items.values('order_number').distinct().count()
            
            if total_orders == 0:
                return JsonResponse({
                    'fully_dispatched': False,
                    'dispatched_orders': 0,
                    'total_orders': 0,
                    'complete_orders': 0,
                    'percentage': 0,
                    'reason': 'No orders found'
                })
            
            platform = picklist.platform.upper()
            order_numbers = picklist_items.values_list('order_number', flat=True).distinct()
            
            dispatched_orders = 0
            complete_orders = 0
            
            for order_number in order_numbers:
                order_status = None
                
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
                
                if order:
                    if order.status == 'Dispatch':
                        dispatched_orders += 1
                    elif order.status == 'Complete':
                        complete_orders += 1
            
            fully_dispatched = dispatched_orders == total_orders
            
            return JsonResponse({
                'fully_dispatched': fully_dispatched,
                'dispatched_orders': dispatched_orders,
                'total_orders': total_orders,
                'complete_orders': complete_orders,
                'percentage': round((dispatched_orders / total_orders) * 100, 1) if total_orders > 0 else 0
            })
        
    except Exception as e:
        print(f"Error in check_picklist_fully_dispatched: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'fully_dispatched': False,
            'dispatched_orders': 0,
            'total_orders': 0,
            'complete_orders': 0,
            'percentage': 0,
            'error': str(e)
        })
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