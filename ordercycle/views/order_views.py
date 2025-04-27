"""
Views for handling order-related functionality.
"""
from django.db.models import Count, Q
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models import (
    AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders,
    Picklist, PicklistItem, MasterTable, PicklistItemLocation
)

class OrderCountsViewSet(ViewSet):
    """ViewSet for getting order counts and processing orders."""
    
    @action(detail=False, methods=['get'])
    def get_counts(self, request):
        """Get counts of orders by platform and type."""
        # Get status from query params, default to 'Ready to Process'
        status = request.query_params.get('status', 'Ready to Process')
        
        # Initialize counts dictionary
        counts = {
            'AMAZON': {'total': 0, 'single': 0, 'multi': 0},
            'FLIPKART': {'total': 0, 'single': 0, 'multi': 0},
            'FIRSTCRY': {'total': 0, 'single': 0, 'multi': 0},
            'MEESHO': {'total': 0, 'single': 0, 'multi': 0}
        }

        # Filter by status for all platforms
        # Amazon orders
        amazon_orders = AmazonOrders.objects.filter(status=status)
        counts['AMAZON']['total'] = amazon_orders.values('order_number').distinct().count()
        counts['AMAZON']['single'] = amazon_orders.filter(order_type='Single').values('order_number').distinct().count()
        counts['AMAZON']['multi'] = amazon_orders.filter(order_type='Multiple').values('order_number').distinct().count()
            
        # Flipkart orders
        flipkart_orders = FlipkarOrders.objects.filter(status=status)
        counts['FLIPKART']['total'] = flipkart_orders.values('order_number').distinct().count()
        counts['FLIPKART']['single'] = flipkart_orders.filter(order_type='Single').values('order_number').distinct().count()
        counts['FLIPKART']['multi'] = flipkart_orders.filter(order_type='Multiple').values('order_number').distinct().count()
            
        # FirstCry orders
        firstcry_orders = FirstcryOrders.objects.filter(status=status)
        counts['FIRSTCRY']['total'] = firstcry_orders.values('order_number').distinct().count()
        counts['FIRSTCRY']['single'] = firstcry_orders.filter(order_type='Single').values('order_number').distinct().count()
        counts['FIRSTCRY']['multi'] = firstcry_orders.filter(order_type='Multiple').values('order_number').distinct().count()

        # Meesho orders
        meesho_orders = MeeshoOrders.objects.filter(status=status)
        counts['MEESHO']['total'] = meesho_orders.values('order_number').distinct().count()
        counts['MEESHO']['single'] = meesho_orders.filter(order_type='Single').values('order_number').distinct().count()
        counts['MEESHO']['multi'] = meesho_orders.filter(order_type='Multiple').values('order_number').distinct().count()
        
        return Response(counts)

    @action(detail=False, methods=['get'])
    def get_single_orders(self, request):
        """Get detailed list of single orders."""
        platform = request.query_params.get('platform', '').upper()
        batch_limit = request.query_params.get('batch_limit', None)
        status = request.query_params.get('status', 'Ready to Process')
        
        # Initialize data as an empty list by default
        data = []
        
        # Get the appropriate model and query based on platform
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        if platform in model_mapping:
            # Get single orders based on order_type field and include only distinct order numbers
            single_orders = model_mapping[platform].objects.filter(
                order_type='Single', 
                status=status
            ).order_by('order_number').distinct('order_number')
            
            # Serialize the data
            data = [{
                'order_number': order.order_number,
                'sku': order.sku,
                'quantity': order.quantity,
                'pdf_url': order.pdf_url
            } for order in single_orders]
        
        # Apply batch limit if provided
        if batch_limit:
            try:
                batch_limit = int(batch_limit)
                data = data[:batch_limit]
            except (ValueError, TypeError):
                # If invalid batch_limit, return all records (no limit)
                pass
        
        return Response(data)

    @action(detail=False, methods=['get'])
    def get_multi_orders(self, request):
        """Get detailed list of multi orders."""
        platform = request.query_params.get('platform', '').upper()
        batch_limit = request.query_params.get('batch_limit', None)
        status = request.query_params.get('status', 'Ready to Process')
        
        # Initialize data as an empty list by default
        data = []
        
        # Get the appropriate model and query based on platform
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        if platform in model_mapping:
            # Get multi orders based on order_type field and include only distinct order numbers
            multi_orders = model_mapping[platform].objects.filter(
                order_type='Multiple', 
                status=status
            ).order_by('order_number').distinct('order_number')
            
            # Serialize the data
            data = [{
                'order_number': order.order_number,
                'sku': order.sku,
                'quantity': order.quantity,
                'pdf_url': order.pdf_url
            } for order in multi_orders]
        
        # Apply batch limit if provided
        if batch_limit:
            try:
                batch_limit = int(batch_limit)
                data = data[:batch_limit]
            except (ValueError, TypeError):
                # If invalid batch_limit, return all records (no limit)
                pass
        
        return Response(data)

    @action(detail=False, methods=['post'])
    def process_orders(self, request):
        """
        Process selected orders with strict batch limit and SKU limit enforcement.
        Orders are sorted by location (P1, P2, etc.) from MasterTable and then by SKU.
        """
        try:
            # Get data from request
            orders = request.data.get('orders', [])
            batch_limit = request.data.get('batch_limit', 50)
            sku_limit = request.data.get('sku_limit', 0)  # Default to 0 (no limit) if not provided
            next_status = request.data.get('next_status', 'Pick')
            platform = request.data.get('platform', 'UNKNOWN').upper()
            order_type = request.data.get('order_type', 'SINGLE').upper()
            
            print(f"Processing orders: platform={platform}, order_type={order_type}, batch_limit={batch_limit}, sku_limit={sku_limit}")
            print(f"Total orders received: {len(orders)}")
            
            # Convert limits to integers
            try:
                batch_limit = int(batch_limit)
                sku_limit = int(sku_limit)
            except (ValueError, TypeError) as e:
                print(f"Error converting limits to int: {e}")
                batch_limit = 50
                sku_limit = 0
            
            # Validate limits
            if batch_limit <= 0:
                batch_limit = 50
            
            # Map order_type from uppercase SINGLE/MULTIPLE to the database format (Single/Multiple)
            db_order_type = 'Single' if order_type == 'SINGLE' else 'Multiple'
            
            # Get the appropriate model based on platform
            model_mapping = {
                'AMAZON': AmazonOrders,
                'FLIPKART': FlipkarOrders,
                'FIRSTCRY': FirstcryOrders,
                'MEESHO': MeeshoOrders
            }
            
            if platform not in model_mapping:
                return Response({
                    'status': 'error',
                    'message': f'Unknown platform: {platform}'
                }, status=400)
                
            order_model = model_mapping[platform]
            
            # Process orders in batches respecting both batch_limit and sku_limit
            processed_orders = []
            created_picklists = []
            
            # Fetch all ready-to-process orders from the provided list
            all_orders = []
            for order_id in orders:
                order = order_model.objects.filter(
                    order_number=order_id,
                    status='Ready to Process'
                ).first()
                
                if order:
                    all_orders.append(order)
            
            if not all_orders:
                return Response({
                    'status': 'error',
                    'message': 'No orders found with the specified criteria',
                }, status=404)
            
            # Create a dictionary to cache location data for SKUs to avoid repeated database lookups
            sku_location_map = {}
            
            # Extract all unique SKUs from orders
            unique_skus = {order.sku for order in all_orders if order.sku}
            
            # Fetch location data from MasterTable for all SKUs in one query
            master_items = MasterTable.objects.filter(sku__in=unique_skus)
            
            # Map SKUs to their locations (using the first location if multiple exist)
            for item in master_items:
                if item.sku not in sku_location_map:
                    sku_location_map[item.sku] = item.location
            
            print(f"Retrieved locations for {len(sku_location_map)} unique SKUs from MasterTable")
            
            # Define a sort key function that uses the location from MasterTable
            def get_sort_key(order):
                location = sku_location_map.get(order.sku, 'ZZZ')  # Default to high value if location not found
                return (location, order.sku)
            
            # Sort orders by location first, then by SKU
            try:
                all_orders.sort(key=get_sort_key)
                print(f"Orders sorted by MasterTable location and SKU")
                # Print first few orders with their locations for debugging
                debug_orders = [f"{sku_location_map.get(o.sku, 'Unknown')}:{o.sku}" for o in all_orders[:5]]
                print(f"First few orders (location:sku): {debug_orders}")
            except Exception as e:
                print(f"Error sorting by location: {e}. Sorting by SKU only.")
                all_orders.sort(key=lambda order: order.sku)
                print(f"Orders sorted by SKU only. First few SKUs: {[o.sku for o in all_orders[:5]]}")
            
            # Process orders in batches, creating new picklists as needed
            remaining_orders = all_orders[:]
            
            while remaining_orders:
                # Create a new picklist for this batch
                picklist_id = Picklist.generate_picklist_id()
                picklist = Picklist.objects.create(
                    picklist_id=picklist_id,
                    picklist_type=order_type,
                    quantity=0,  # Will update after processing
                    platform=platform,
                    status='CREATED'
                )
                created_picklists.append(picklist_id)
                
                current_batch = []
                unique_skus = set()
                
                # Fill the current batch respecting both limits
                for order in remaining_orders[:]:
                    # Check if adding this order would exceed the SKU limit
                    if sku_limit > 0 and order.sku not in unique_skus and len(unique_skus) >= sku_limit:
                        # SKU limit would be exceeded, don't add this order to current batch
                        continue
                    
                    # Check if adding this order would exceed the batch limit
                    if len(current_batch) >= batch_limit:
                        # Batch limit reached, don't add more orders
                        break
                    
                    # Add this order to the current batch
                    current_batch.append(order)
                    unique_skus.add(order.sku)
                    remaining_orders.remove(order)
                
                # Process the current batch
                for order in current_batch:
                    # Update order status
                    order.status = next_status
                    order.save()
                    
                    # Get location from our cache map
                    location = sku_location_map.get(order.sku, 'Unknown')
                    
                    # Create picklist item
                    PicklistItem.objects.create(
                        picklist=picklist,
                        order_number=order.order_number,
                        sku=order.sku,
                        quantity=order.quantity
                    )
                    
                    processed_orders.append(order.order_number)
                
                # Update picklist quantity
                if current_batch:
                    picklist.quantity = len(current_batch)
                    picklist.save()
                else:
                    # No orders were processed in this batch, delete the picklist
                    picklist.delete()
                    created_picklists.pop()  # Remove this picklist ID from the list
            
            if not processed_orders:
                return Response({
                    'status': 'error',
                    'message': 'No orders could be processed with the specified criteria',
                }, status=404)
            
            return Response({
                'status': 'success',
                'message': f'Processed {len(processed_orders)} {platform} orders across {len(created_picklists)} picklists',
                'processed_count': len(processed_orders),
                'total_count': len(orders),
                'batch_limit': batch_limit,
                'sku_limit': sku_limit,
                'processed_orders': processed_orders,
                'picklist_ids': created_picklists,
                'main_picklist_id': created_picklists[0] if created_picklists else None
            })
            
        except Exception as e:
            import traceback
            print(f"Error in process_orders: {str(e)}")
            traceback.print_exc()
            
            return Response({
                'status': 'error',
                'message': f'Error processing orders: {str(e)}',
            }, status=500)