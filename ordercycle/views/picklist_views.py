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
        (CREATED first, then others) and then by created_at date
        """
        status = request.query_params.get('status', None)
        
        if status:
            picklists = Picklist.objects.filter(status=status)
        else:
            picklists = Picklist.objects.all()
        
        # Define a custom sorting order for statuses
        # This will ensure CREATED appears before PRINTED and other statuses
        status_order = {
            'CREATED': 1,
            'PRINTED': 2,
            'PACKING': 3,
            # Add other statuses as needed with appropriate numbers
        }
        
        # Convert queryset to list for custom sorting
        picklists_list = list(picklists)
        
        # Custom sorting: first by status order, then by created_at date (descending)
        picklists_list.sort(
            key=lambda p: (
                status_order.get(p.status, 999),  # Default to a high number for undefined statuses
                -p.created_at.timestamp()  # Negative timestamp for descending date order
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
            items = picklist.items.all().prefetch_related('location_info')  # Use prefetch_related to optimize
            
            # Get all active pickers
            pickers = Picker.objects.filter(is_active=True).values('picker_id', 'name')
            
            # Get items with enhanced data
            detailed_items = []
            for item in items:
                # Get location info if available
                try:
                    location_info = getattr(item, 'location_info', None)
                    
                    if location_info:
                        location = location_info.location
                        picked = location_info.picked
                        picker_id = location_info.picker.picker_id if location_info.picker else None
                    else:
                        # Try to get location from MasterTable
                        master_item = MasterTable.objects.filter(sku=item.sku).first()
                        location = master_item.location if master_item else "Unknown"
                        picked = False
                        picker_id = None
                        
                        # Create location info if it doesn't exist but we have location data
                        if master_item and master_item.location:
                            location_info, created = PicklistItemLocation.objects.get_or_create(
                                picklist_item=item,
                                defaults={
                                    'location': master_item.location,
                                    'picked': False
                                }
                            )
                except Exception as e:
                    # If any error occurs, use default values
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
            
            # Sort the items by SKU in descending order by default
            detailed_items.sort(key=lambda x: x['sku'], reverse=True)
            
            return Response({
                'picklist_id': picklist.picklist_id,
                'picklist_type': picklist.picklist_type,
                'status': picklist.status,
                'platform': picklist.platform,
                'items': detailed_items,
                'pickers': list(pickers),
                'created_at': picklist.created_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(picklist, 'created_at') else None
            })
        
        except Picklist.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Picklist not found'
            }, status=404)
        
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
            
            return Response({
                'status': 'success',
                'message': f'Assigned picker {picker_id} to {updated_count} items'
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
                # Get the appropriate model
                order_model = model_mapping[platform]
                
                # Delete orders that match the order numbers in this picklist
                deleted_orders_count = order_model.objects.filter(
                    order_number__in=order_numbers,
                    status='Pick'  # Only delete orders that are in 'Pick' status (part of this picklist)
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