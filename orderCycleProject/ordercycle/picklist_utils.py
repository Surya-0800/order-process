# # yourapp/picklist_utils.py
# from django.db import transaction
# from django.utils import timezone
# from django.db.models import Count, F, Q
# from .models import Picklist, PicklistItem, Order, Picker, MasterTable

# def get_next_picklist_id():
#     """Generate the next sequential picklist ID"""
#     last_picklist = Picklist.objects.order_by('-picklist_id').first()
    
#     # If no picklists exist, start with 111001
#     if not last_picklist:
#         return "111001"
    
#     try:
#         # Get the last ID and increment by 1
#         last_id = int(last_picklist.picklist_id)
#         return str(last_id + 1)
#     except ValueError:
#         # Fallback if the ID format is not numeric
#         return f"111{Picklist.objects.count() + 1:03d}"

# @transaction.atomic
# def create_picklist(order_ids, picklist_type, picker_id=None):
#     """
#     Create a new picklist from order IDs
    
#     Args:
#         order_ids (list): List of order IDs to include in the picklist
#         picklist_type (str): Type of picklist ('SINGLE' or 'MULTI')
#         picker_id (str, optional): ID of the picker assigned to this picklist
        
#     Returns:
#         Picklist: The newly created picklist object
#     """
#     # Get the orders
#     orders = Order.objects.filter(order_id__in=order_ids, status='READY_TO_PICK')
    
#     # If no orders found, return None
#     if not orders.exists():
#         return None
    
#     # Get the picker if provided
#     picker = None
#     if picker_id:
#         try:
#             picker = Picker.objects.get(picker_id=picker_id)
#         except Picker.DoesNotExist:
#             pass
    
#     # Create the picklist
#     picklist_id = get_next_picklist_id()
#     picklist = Picklist.objects.create(
#         picklist_id=picklist_id,
#         picklist_type=picklist_type,
#         picker=picker,
#         status='CREATED'
#     )
    
#     # Add items to the picklist
#     for order in orders:
#         # Look up location in MasterTable if not set in order
#         if not order.location:
#             # Try to get location from master table
#             master_item = MasterTable.objects.filter(sku=order.sku).first()
#             location = master_item.location if master_item else "Unknown"
#         else:
#             location = order.location
        
#         # Create picklist item
#         PicklistItem.objects.create(
#             picklist=picklist,
#             order_id=order.order_id,
#             sku=order.sku,
#             quantity=order.quantity,
#             location=location
#         )
        
#         # Update order status
#         order.status = 'PICKING'
#         order.save()
    
#     return picklist

# def get_picklists(status=None):
#     """
#     Get all picklists, optionally filtered by status
    
#     Args:
#         status (str, optional): Filter picklists by status
        
#     Returns:
#         QuerySet: Filtered picklists
#     """
#     if status:
#         return Picklist.objects.filter(status=status).order_by('-created_at')
#     return Picklist.objects.all().order_by('-created_at')

# def get_picklist_details(picklist_id):
#     """
#     Get detailed information about a picklist
    
#     Args:
#         picklist_id (str): Picklist ID
        
#     Returns:
#         dict: Picklist details including items
#     """
#     try:
#         picklist = Picklist.objects.get(picklist_id=picklist_id)
#         items = picklist.picklistitems.all().order_by('-sku', 'location')
        
#         return {
#             'picklist_id': picklist.picklist_id,
#             'picklist_type': picklist.get_picklist_type_display(),
#             'status': picklist.get_status_display(),
#             'picker': picklist.picker.picker_id if picklist.picker else None,
#             'created_at': picklist.created_at,
#             'printed_at': picklist.printed_at,
#             'completed_at': picklist.completed_at,
#             'item_count': picklist.item_count,
#             'picked_count': picklist.picked_count,
#             'items': [{
#                 'id': item.id,
#                 'order_id': item.order_id,
#                 'sku': item.sku,
#                 'quantity': item.quantity,
#                 'location': item.location,
#                 'picked': item.picked,
#                 'picked_at': item.picked_at
#             } for item in items]
#         }
#     except Picklist.DoesNotExist:
#         return None

# def update_picklist_status(picklist_id, new_status):
#     """
#     Update the status of a picklist
    
#     Args:
#         picklist_id (str): Picklist ID
#         new_status (str): New status ('CREATED', 'PRINTED', 'PACKING', 'COMPLETED')
        
#     Returns:
#         bool: True if update was successful, False otherwise
#     """
#     try:
#         picklist = Picklist.objects.get(picklist_id=picklist_id)
#         picklist.status = new_status
        
#         # Update timestamps based on status
#         if new_status == 'PRINTED':
#             picklist.printed_at = timezone.now()
#         elif new_status == 'COMPLETED':
#             picklist.completed_at = timezone.now()
            
#             # Update all orders in this picklist to 'PICKED'
#             order_ids = picklist.picklistitems.values_list('order_id', flat=True)
#             Order.objects.filter(order_id__in=order_ids).update(status='PICKED')
        
#         picklist.save()
#         return True
#     except Picklist.DoesNotExist:
#         return False

# def mark_items_as_picked(picklist_id, item_ids=None):
#     """
#     Mark specific items in a picklist as picked
    
#     Args:
#         picklist_id (str): Picklist ID
#         item_ids (list, optional): List of item IDs to mark as picked
#                                    If None, all items will be marked
        
#     Returns:
#         int: Number of items marked as picked
#     """
#     try:
#         picklist = Picklist.objects.get(picklist_id=picklist_id)
#         items_query = picklist.picklistitems.all()
        
#         if item_ids:
#             items_query = items_query.filter(id__in=item_ids)
            
#         # Mark items as picked
#         count = 0
#         for item in items_query.filter(picked=False):
#             item.picked = True
#             item.picked_at = timezone.now()
#             item.save()
#             count += 1
        
#         # Check if all items are picked
#         if picklist.picklistitems.filter(picked=False).count() == 0:
#             # If all items are picked, update the picklist status
#             if picklist.status == 'CREATED' or picklist.status == 'PRINTED':
#                 picklist.status = 'PACKING'
#                 picklist.save()
        
#         return count
#     except Picklist.DoesNotExist:
#         return 0

# def assign_picker_to_picklist(picklist_id, picker_id):
#     """
#     Assign a picker to a picklist
    
#     Args:
#         picklist_id (str): Picklist ID
#         picker_id (str): Picker ID
        
#     Returns:
#         bool: True if assignment was successful, False otherwise
#     """
#     try:
#         picklist = Picklist.objects.get(picklist_id=picklist_id)
#         picker = Picker.objects.get(picker_id=picker_id)
        
#         picklist.picker = picker
#         picklist.save()
#         return True
#     except (Picklist.DoesNotExist, Picker.DoesNotExist):
#         return False

# def get_orders_for_picklist(order_type=None, sort_by='sku', sort_order='desc', location=None):
#     """
#     Get orders that are ready to be picked
    
#     Args:
#         order_type (str, optional): Filter by order type ('SINGLE' or 'MULTIPLE')
#         sort_by (str, optional): Field to sort by ('sku', 'location', etc.)
#         sort_order (str, optional): Sort direction ('asc' or 'desc')
#         location (str, optional): Filter by location
        
#     Returns:
#         QuerySet: Filtered and sorted orders
#     """
#     # Start with orders ready to pick
#     orders = Order.objects.filter(status='READY_TO_PICK')
    
#     # Apply filters
#     if order_type:
#         orders = orders.filter(order_type=order_type)
    
#     if location:
#         orders = orders.filter(location=location)
    
#     # Apply sorting
#     order_field = sort_by
#     if sort_order == 'desc':
#         order_field = f"-{sort_by}"
    
#     return orders.order_by(order_field)

# def get_all_pickers():
#     """
#     Get all active pickers
    
#     Returns:
#         QuerySet: All active pickers
#     """
#     return Picker.objects.filter(is_active=True)