"""
Views for handling picklist-related functionality.
"""
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models import (
    Picklist, PicklistItem, PicklistItemLocation, Picker, MasterTable,AmazonOrders,FlipkarOrders,FirstcryOrders,MeeshoOrders
)

class PicklistViewSet(ViewSet):
    """ViewSet for picklist management."""
    
    def list(self, request):
        """
        List all picklists - this is the method that handles GET /api/picklists/
        """
        return self.get_picklists(request)
        
    def retrieve(self, request, pk=None):
        """
        Retrieve a specific picklist - this is the method that handles GET /api/picklists/{id}/
        """
        return self.get_picklist_items(request, pk)
    
    @action(detail=False, methods=['get'])
    def get_picklists(self, request):
        """
        Get all picklists with optional status filter and sorted by status
        """
        status = request.query_params.get('status', None)
        
        if status:
            picklists = Picklist.objects.filter(status=status)
        else:
            picklists = Picklist.objects.all()
        
        # Define a custom sorting order for statuses
        status_order = {
            'CREATED': 1,
            'PRINTED': 2,
            'PACKING': 3,
            'PARTIAL_DISPATCH': 4,
            'DISPATCH': 5,
        }
        
        # Convert queryset to list for custom sorting
        picklists_list = list(picklists)
        
        # Custom sorting: first by status order, then by created_at date (descending)
        picklists_list.sort(
            key=lambda p: (
                status_order.get(p.status, 999),
                -p.created_at.timestamp()
            )
        )
        
        data = [{
            'picklist_id': picklist.picklist_id,
            'picklist_type': picklist.picklist_type,
            'quantity': picklist.quantity,
            'status': picklist.status,
            'platform': picklist.platform,
            'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for picklist in picklists_list]
        
        return Response(data)
    
    
    @action(detail=True, methods=['get'])
    def get_picklist_items(self, request, pk=None):
        """
        Get all items in a picklist with location information if available
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            items = picklist.items.all().prefetch_related('location_info')
            
            # Get all active pickers
            pickers = Picker.objects.filter(is_active=True).values('picker_id', 'name')
            
            # Check if picklist has an assigned picker
            assigned_picker_id = None
            assigned_picker_name = None
            
            first_picker_info = PicklistItemLocation.objects.filter(
                picklist_item__picklist=picklist,
                picker__isnull=False
            ).select_related('picker').first()
            
            if first_picker_info and first_picker_info.picker:
                assigned_picker_id = first_picker_info.picker.picker_id
                assigned_picker_name = first_picker_info.picker.name
            
            # Get items with enhanced data
            detailed_items = []
            for item in items:
                try:
                    location_info = getattr(item, 'location_info', None)
                    
                    if location_info:
                        location = location_info.location
                        picked = location_info.picked
                        picker_id = location_info.picker.picker_id if location_info.picker else None
                    else:
                        master_item = MasterTable.objects.filter(sku=item.sku).first()
                        location = master_item.location if master_item else "Unknown"
                        picked = False
                        picker_id = None
                        
                        if master_item and master_item.location:
                            location_info, created = PicklistItemLocation.objects.get_or_create(
                                picklist_item=item,
                                defaults={
                                    'location': master_item.location,
                                    'picked': False
                                }
                            )
                except Exception as e:
                    location = "Unknown"
                    picked = False
                    picker_id = None
                
                detailed_items.append({
                    'id': item.id,
                    'order_number': item.order_number,
                    'sku': item.sku,
                    'quantity': item.quantity,
                    'location': location,
                    'picked': picked,
                    'picker_id': picker_id
                })
            
            detailed_items.sort(key=lambda x: x['sku'], reverse=True)

            orders = set() 
            for i in detailed_items:
                orders.add(i["order_number"])
            
            return Response({
                'picklist_id': picklist.picklist_id,
                'picklist_type': picklist.picklist_type,
                'status': picklist.status,
                'platform': picklist.platform,
                'picker_id': assigned_picker_id,
                'picker_name': assigned_picker_name,
                'items': detailed_items,
                'pickers': list(pickers),
                'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(picklist, 'created_at') else None,
                'total_orders': len(orders),
                'total_items':len(items)
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)
        
    @action(detail=True, methods=['post'])
    def mark_printed_only(self, request, pk=None):
        """
        Mark order as printed but NOT processed - only for printing stage
        This doesn't change order status, just marks it as printed for tracking
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            order_number = request.data.get('order_number')
            
            if not order_number:
                return Response({
                    'status': 'error',
                    'message': 'Order number is required'
                }, status=400)
            
            # Get the platform model
            platform = picklist.platform.upper()
            model_mapping = {
                'AMAZON': AmazonOrders,
                'FLIPKART': FlipkarOrders,
                'FIRSTCRY': FirstcryOrders,
                'MEESHO': MeeshoOrders
            }
            
            if platform not in model_mapping:
                return Response({
                    'status': 'error',
                    'message': f'Invalid platform: {platform}'
                }, status=400)
            
            order_model = model_mapping[platform]
            
            # Update order with is_printed flag but keep status as 'Pick'
            updated_count = order_model.objects.filter(
                order_number=order_number
            ).update(
                is_printed=True,  # New field to track printing
                printed_at=timezone.now()
            )
            
            if updated_count == 0:
                return Response({
                    'status': 'error',
                    'message': f'Order {order_number} not found'
                }, status=404)
            
            return Response({
                'status': 'success',
                'message': f'Order {order_number} marked as printed. Awaiting AWB validation.'
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Error marking order as printed: {str(e)}'
            }, status=500)
        
    @action(detail=True, methods=['post'])
    def validate_awb_and_complete(self, request, pk=None):
        """
        Validate AWB and mark order as complete if validation passes
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            order_number = request.data.get('order_number')
            awb = request.data.get('awb')
            
            if not order_number or not awb:
                return Response({
                    'status': 'error',
                    'message': 'Order number and AWB are required'
                }, status=400)
            
            # Get the platform model
            platform = picklist.platform.upper()
            model_mapping = {
                'AMAZON': AmazonOrders,
                'FLIPKART': FlipkarOrders,
                'FIRSTCRY': FirstcryOrders,
                'MEESHO': MeeshoOrders
            }
            
            if platform not in model_mapping:
                return Response({
                    'status': 'error',
                    'message': f'Invalid platform: {platform}'
                }, status=400)
            
            order_model = model_mapping[platform]
            
            # Get all matching orders (handles duplicates)
            # Get all matching orders
            matching_orders = order_model.objects.filter(order_number=order_number)

            if not matching_orders.exists():
                return Response({
                    'status': 'error',
                    'message': f'Order {order_number} not found'
                }, status=404)

            # Validate AWB against existing AWB in database (use correct field name)
            first_order = matching_orders.first()
            if hasattr(first_order, 'AWB') and first_order.AWB:  # Changed from 'awb' to 'AWB'
                if first_order.AWB.strip() != awb.strip():
                    return Response({
                        'status': 'error',
                        'message': f'AWB mismatch. Expected: {first_order.AWB}, Provided: {awb}',
                        'awb_match': False
                    }, status=400)

            # AWB validation passed - mark ALL matching orders as complete
            updated_count = matching_orders.update(
                status='Complete',
                is_validated=True,
                AWB=awb.strip(),  # Changed from 'awb' to 'AWB'
                validated_at=timezone.now()
            )
            
            # Check if all orders in picklist are complete and update picklist status
            self._update_picklist_status(picklist)
            
            return Response({
                'status': 'success',
                'message': f'AWB validated successfully. Order {order_number} marked as Complete.',
                'awb_match': True
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Error validating AWB: {str(e)}'
            }, status=500)
        
    def _update_picklist_status(self, picklist):
        """
        Update picklist status based on order statuses
        """
        platform = picklist.platform.upper()
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        if platform not in model_mapping:
            return
        
        order_model = model_mapping[platform]
        
        # Get all unique order numbers in this picklist
        picklist_order_numbers = list(
            picklist.items.values_list('order_number', flat=True).distinct()
        )
        
        # Get status for each unique order number (taking the first occurrence for duplicates)
        order_status_map = {}
        for order_number in picklist_order_numbers:
            # Get the first order record for this order number
            order = order_model.objects.filter(order_number=order_number).first()
            if order:
                order_status_map[order_number] = order.status
        
        # Count statuses by unique order numbers
        status_counts = {}
        for order_number, status in order_status_map.items():
            status_counts[status] = status_counts.get(status, 0) + 1
        
        total_orders = len(picklist_order_numbers)
        complete_orders = status_counts.get('Complete', 0)
        processed_orders = status_counts.get('Processed', 0)
        dispatch_orders = status_counts.get('Dispatch', 0)
        
        # Update picklist status based on order distribution
        if complete_orders == total_orders:
            # All orders are complete - ready for dispatch
            picklist.status = 'DISPATCH'
        elif dispatch_orders > 0:
            # Some orders are already dispatched
            if dispatch_orders == total_orders:
                picklist.status = 'DISPATCH'
            else:
                picklist.status = 'PARTIAL_DISPATCH'
        elif (complete_orders + processed_orders) == total_orders:
            # All orders are either complete or processed
            if complete_orders > 0:
                if complete_orders == total_orders:
                    # All are complete
                    picklist.status = 'DISPATCH'
                else:
                    # Mix of complete and processed
                    picklist.status = 'PARTIAL_DISPATCH'
            else:
                # All processed but none complete
                picklist.status = 'PACKING'
        else:
            # Still have pending orders (Pick status or other)
            picklist.status = 'PACKING'
        
        picklist.save()


    @action(detail=True, methods=['post'])
    def skip_awb_validation(self, request, pk=None):
        """
        Skip AWB validation and mark order as processed (not complete)
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            order_number = request.data.get('order_number')
            
            if not order_number:
                return Response({
                    'status': 'error',
                    'message': 'Order number is required'
                }, status=400)
            
            # Get the platform model
            platform = picklist.platform.upper()
            model_mapping = {
                'AMAZON': AmazonOrders,
                'FLIPKART': FlipkarOrders,
                'FIRSTCRY': FirstcryOrders,
                'MEESHO': MeeshoOrders
            }
            
            if platform not in model_mapping:
                return Response({
                    'status': 'error',
                    'message': f'Invalid platform: {platform}'
                }, status=400)
            
            order_model = model_mapping[platform]
            
            # Mark as processed but not complete
            updated_count = order_model.objects.filter(
                order_number=order_number
            ).update(
                status='Processed',  # Different from 'Complete'
                is_validated=False,
                processed_at=timezone.now()
            )
            
            if updated_count == 0:
                return Response({
                    'status': 'error',
                    'message': f'Order {order_number} not found'
                }, status=404)
            
            # Update picklist status
            self._update_picklist_status(picklist)
            
            return Response({
                'status': 'success',
                'message': f'Order {order_number} marked as Processed. AWB validation can be done later.'
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Error processing order: {str(e)}'
            }, status=500)
    
    
    
    @action(detail=True, methods=['post'])
    def undo_picked(self, request, pk=None):
        """
        Undo picked status for items in a picklist
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            item_ids = request.data.get('item_ids', [])
            
            if not item_ids:
                return Response({
                    'status': 'error',
                    'message': 'No items specified'
                }, status=400)
            
            # Update picked status for all specified items
            updated_count = 0
            
            for item_id in item_ids:
                try:
                    # Get the picklist item
                    item = PicklistItem.objects.get(id=item_id, picklist=picklist)
                    
                    # Get or create location info if it doesn't exist
                    location_info, created = PicklistItemLocation.objects.get_or_create(
                        picklist_item=item,
                        defaults={'location': 'Unknown', 'picked': False}
                    )
                    
                    # Set picked to False
                    location_info.picked = False
                    location_info.picked_at = None  # Clear the picked timestamp
                    location_info.save()
                    
                    updated_count += 1
                except PicklistItem.DoesNotExist:
                    continue
            
            # Update picklist status if needed
            if picklist.status == 'PRINTED' or picklist.status == 'PACKING':
                # If at least one item is unpicked, change status back to CREATED
                picklist.status = 'CREATED'
                picklist.save()
            
            return Response({
                'status': 'success',
                'message': f'Unmarked {updated_count} items as picked. Picklist status set to CREATED.'
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)

    @action(detail=True, methods=['post'])
    def mark_picked(self, request, pk=None):
        """
        Mark items in a picklist as picked
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            order_numbers = request.data.get('order_numbers', [])
            
            if not order_numbers:
                return Response({
                    'status': 'error',
                    'message': 'No orders specified'
                }, status=400)
            
            # Mark items as picked
            updated_count = PicklistItem.objects.filter(
                picklist=picklist,
                order_number__in=order_numbers
            ).update(picked=True)
            
            # Check if all items are picked
            if picklist.items.filter(picked=False).count() == 0:
                if picklist.status != 'PACKING':
                    picklist.status = 'PACKING'
                    picklist.save()
                
                return Response({
                    'status': 'success',
                    'message': f'All items marked as picked. Picklist moved to PACKING status.'
                })
            else:
                return Response({
                    'status': 'success',
                    'message': f'{updated_count} items marked as picked'
                })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)  
        
    @action(detail=True, methods=['get'])
    def get_detailed_items(self, request, pk=None):
        """
        Get detailed picklist items with location information
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            items = picklist.items.all().select_related('location_info')
            
            # Get all active pickers
            pickers = Picker.objects.filter(is_active=True).values('picker_id', 'name')
            
            # Get items with location data
            detailed_items = []
            for item in items:
                location_info = getattr(item, 'location_info', None)
                
                # Try to get location from MasterTable if not available
                location = "Unknown"
                picked = False
                picker_id = None
                
                if location_info:
                    location = location_info.location
                    picked = location_info.picked
                    picker_id = location_info.picker.picker_id if location_info.picker else None
                else:
                    # Try to get location from MasterTable
                    try:
                        master_item = MasterTable.objects.filter(sku=item.sku).first()
                        if master_item:
                            location = master_item.location
                            
                            # Create location info if it doesn't exist
                            location_info, created = PicklistItemLocation.objects.get_or_create(
                                picklist_item=item,
                                defaults={'location': location, 'picked': False}
                            )
                    except Exception as e:
                        print(f"Error finding location: {e}")
                
                detailed_items.append({
                    'id': item.id,
                    'order_number': item.order_number,
                    'sku': item.sku,
                    'quantity': item.quantity,
                    'location': location,
                    'picked': picked,
                    'picker_id': picker_id
                })
            
            return Response({
                'picklist_id': picklist.picklist_id,
                'picklist_type': picklist.picklist_type,
                'status': picklist.status,
                'platform': picklist.platform,
                'items': detailed_items,
                'pickers': list(pickers)
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)

    @action(detail=True, methods=['post'])
    def assign_picker(self, request, pk=None):
        """
        Assign a picker to picklist items
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            picker_id = request.data.get('picker_id')
            item_ids = request.data.get('item_ids', [])
            
            if not picker_id:
                return Response({
                    'status': 'error',
                    'message': 'Picker ID is required'
                }, status=400)
            
            try:
                picker = Picker.objects.get(picker_id=picker_id)
            except Picker.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': f'Picker with ID {picker_id} not found'
                }, status=404)
            
            # If no specific items provided, assign picker to all items
            if not item_ids:
                item_ids = list(picklist.items.values_list('id', flat=True))
            
            # Update location info for all specified items
            updated_count = 0
            for item_id in item_ids:
                try:
                    item = PicklistItem.objects.get(id=item_id, picklist=picklist)
                    
                    # Get or create location info
                    location_info, created = PicklistItemLocation.objects.get_or_create(
                        picklist_item=item,
                        defaults={'location': 'Unknown', 'picked': False}
                    )
                    
                    # Assign picker
                    location_info.picker = picker
                    location_info.save()
                    updated_count += 1
                    
                except PicklistItem.DoesNotExist:
                    continue
            
            # Get picker name for response
            picker_name = picker.name if hasattr(picker, 'name') and picker.name else picker_id
            
            return Response({
                'status': 'success',
                'message': f'Assigned picker {picker_name} ({picker_id}) to {updated_count} items',
                'picker_id': picker_id,
                'picker_name': picker_name
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)
        
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """
        Update the status of a picklist
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            new_status = request.data.get('status')
            
            if not new_status:
                return Response({
                    'status': 'error',
                    'message': 'No status specified'
                }, status=400)
            
            # Update the picklist status
            old_status = picklist.status
            picklist.status = new_status
            picklist.save()
            
            return Response({
                'status': 'success',
                'message': f'Picklist status updated from {old_status} to {new_status}'
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)

    @action(detail=True, methods=['post'])
    def mark_items_picked(self, request, pk=None):
        """
        Mark picklist items as picked
        """
        try:
            picklist = Picklist.objects.get(picklist_id=pk)
            item_ids = request.data.get('item_ids', [])
            
            if not item_ids:
                return Response({
                    'status': 'error',
                    'message': 'No items specified'
                }, status=400)
            
            # Update picked status for all specified items
            updated_count = 0
            for item_id in item_ids:
                try:
                    item = PicklistItem.objects.get(id=item_id, picklist=picklist)
                    
                    # Get or create location info
                    location_info, created = PicklistItemLocation.objects.get_or_create(
                        picklist_item=item,
                        defaults={'location': 'Unknown', 'picked': False}
                    )
                    
                    # Mark as picked
                    location_info.picked = True
                    location_info.picked_at = timezone.now()
                    location_info.save()
                    updated_count += 1
                    
                except PicklistItem.DoesNotExist:
                    continue
            
            # Check if all items are picked (for information only)
            all_picked = not PicklistItemLocation.objects.filter(
                picklist_item__picklist=picklist, 
                picked=False
            ).exists()
            
            # We're not changing the status to PRINTED here anymore
            # This will be handled by the print button
            
            return Response({
                'status': 'success',
                'message': f'Marked {updated_count} items as picked',
                'all_picked': all_picked
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)
        
    @action(detail=True, methods=['delete'])
    def delete_picklist(self, request, pk=None):
        """
        Delete a picklist and all its associated orders from the database
        """
        try:
            picklist = get_object_or_404(Picklist, picklist_id=pk)
            
            # Get all items in the picklist
            picklist_items = PicklistItem.objects.filter(picklist=picklist)
            
            # Get distinct order numbers and platform from the items
            order_numbers = list(picklist_items.values_list('order_number', flat=True).distinct())
            platform = picklist.platform
            
            # Delete orders from the appropriate platform table
            model_mapping = {
                'AMAZON': AmazonOrders,
                'FLIPKART': FlipkarOrders,
                'FIRSTCRY': FirstcryOrders,
                'MEESHO': MeeshoOrders
            }
            
            if platform in model_mapping:
                order_model = model_mapping[platform]
                
                # Delete orders that match the order numbers in this picklist
                deleted_orders_count = order_model.objects.filter(
                    order_number__in=order_numbers,
                    status__in=['Pick', 'Processed']  # Include both Pick and Processed
                ).delete()[0]
            else:
                deleted_orders_count = 0
            
            # Delete all picklist item locations
            PicklistItemLocation.objects.filter(picklist_item__in=picklist_items).delete()
            
            # Delete all picklist items
            picklist_items.delete()
            
            # Delete the picklist itself
            picklist.delete()
            
            return Response({
                'status': 'success',
                'message': f'Picklist {pk} and all its items deleted successfully. {deleted_orders_count} orders were also deleted.'
            })
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            return Response({
                'status': 'error',
                'message': f'Error deleting picklist: {str(e)}'
            }, status=500)
        
    @action(detail=False, methods=['post'])
    def delete_picklists(self, request):
        """
        Delete multiple picklists and their associated orders in bulk
        """
        try:
            picklist_ids = request.data.get('picklist_ids', [])
            
            if not picklist_ids:
                return Response({
                    'status': 'error',
                    'message': 'No picklist IDs provided'
                }, status=400)
            
            picklists_deleted = 0
            orders_deleted = 0
            
            for picklist_id in picklist_ids:
                try:
                    picklist = Picklist.objects.get(picklist_id=picklist_id)
                    
                    # Get all items in the picklist
                    picklist_items = PicklistItem.objects.filter(picklist=picklist)
                    
                    # Get distinct order numbers and platform from the items
                    order_numbers = list(picklist_items.values_list('order_number', flat=True).distinct())
                    platform = picklist.platform
                    
                    # Delete orders from the appropriate platform table
                    model_mapping = {
                        'AMAZON': AmazonOrders,
                        'FLIPKART': FlipkarOrders,
                        'FIRSTCRY': FirstcryOrders,
                        'MEESHO': MeeshoOrders
                    }
                    
                    if platform in model_mapping:
                        # Get the appropriate model
                        order_model = model_mapping[platform]
                        
                        # Delete orders that match the order numbers in this picklist
                        deleted_count = order_model.objects.filter(
                            order_number__in=order_numbers,
                            status='Pick'  # Only delete orders that are in 'Pick' status (part of this picklist)
                        ).delete()[0]
                        
                        orders_deleted += deleted_count
                    
                    # Delete all picklist item locations
                    PicklistItemLocation.objects.filter(picklist_item__in=picklist_items).delete()
                    
                    # Delete all picklist items
                    picklist_items.delete()
                    
                    # Delete the picklist itself
                    picklist.delete()
                    
                    picklists_deleted += 1
                    
                except Picklist.DoesNotExist:
                    # Skip non-existent picklists
                    continue
            
            if picklists_deleted == 0:
                return Response({
                    'status': 'warning',
                    'message': 'No picklists were found to delete'
                })
            
            return Response({
                'status': 'success',
                'message': f'Successfully deleted {picklists_deleted} picklists and {orders_deleted} associated orders'
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            return Response({
                'status': 'error',
                'message': f'Error deleting picklists: {str(e)}'
            }, status=500)