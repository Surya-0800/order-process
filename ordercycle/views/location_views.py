"""
Views for handling location-based order processing with location grouping.
"""
from django.db.models import Count, Q
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models import (
    AmazonOrders, FlipkarOrders, FirstcryOrders, MeeshoOrders,
    Picklist, PicklistItem, MasterTable, PicklistItemLocation
)

class LocationOrdersViewSet(ViewSet):
    """API for location-based order processing."""
    
    def _get_location_prefix(self, location):
        """Extract location prefix (everything before first hyphen)"""
        if not location or location == "Unknown":
            return location
        return location.split('-')[0] if '-' in location else location
    
    @action(detail=False, methods=['get'])
    def location_counts(self, request):
        """
        Get order counts by location prefix including unknown locations
        """
        platform = request.query_params.get('platform', 'AMAZON')
        order_type = request.query_params.get('order_type', 'single')
        status = request.query_params.get('status', 'Ready to Process')
        
        # Determine which model to use based on platform
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        platform_upper = platform.upper()
        if platform_upper not in model_mapping:
            return Response({
                'error': f'Unknown platform: {platform}'
            }, status=400)
            
        order_model = model_mapping[platform_upper]
        
        # Filter by order type and status
        db_order_type = 'Single' if order_type.lower() == 'single' else 'Multiple'
        orders = order_model.objects.filter(
            order_type=db_order_type,
            status=status
        )
        
        # Get all SKUs in orders
        all_order_skus = list(orders.values_list('sku', flat=True))
        
        # Get known SKUs from MasterTable
        known_skus = MasterTable.objects.filter(
            sku__in=all_order_skus
        ).values_list('sku', flat=True).distinct()
        
        # Get unknown SKUs (not in MasterTable)
        unknown_skus = set(all_order_skus) - set(known_skus)
        
        # Group by location prefix
        location_prefix_data = {}
        
        # Process known locations
        for order in orders:
            # Find the location(s) for this SKU
            locations = MasterTable.objects.filter(sku=order.sku)
            
            if locations.exists():
                for loc in locations:
                    # Get location prefix
                    location_prefix = self._get_location_prefix(loc.location)
                    
                    if location_prefix not in location_prefix_data:
                        location_prefix_data[location_prefix] = {
                            'count': 1,
                            'order_ids': [order.order_number],
                            'full_locations': [loc.location]
                        }
                    else:
                        location_prefix_data[location_prefix]['count'] += 1
                        if order.order_number not in location_prefix_data[location_prefix]['order_ids']:
                            location_prefix_data[location_prefix]['order_ids'].append(order.order_number)
                        if loc.location not in location_prefix_data[location_prefix]['full_locations']:
                            location_prefix_data[location_prefix]['full_locations'].append(loc.location)
            else:
                # Add to "Unknown" location
                if "Unknown" not in location_prefix_data:
                    location_prefix_data["Unknown"] = {
                        'count': 1,
                        'order_ids': [order.order_number],
                        'full_locations': ["Unknown"]
                    }
                else:
                    location_prefix_data["Unknown"]['count'] += 1
                    if order.order_number not in location_prefix_data["Unknown"]['order_ids']:
                        location_prefix_data["Unknown"]['order_ids'].append(order.order_number)
        
        # Format the response
        response_data = {
            'total_orders': orders.count(),
            'locations': []
        }
        
        for location_prefix, data in location_prefix_data.items():
            response_data['locations'].append({
                'location': location_prefix,
                'count': data['count'],
                'order_count': len(data['order_ids']),
                'full_locations': data['full_locations'],  # Include all specific locations in this prefix
                'specific_location_count': len(data['full_locations'])  # How many specific locations are grouped here
            })
        
        # Sort by count descending
        response_data['locations'] = sorted(
            response_data['locations'], 
            key=lambda x: x['count'], 
            reverse=True
        )
        
        return Response(response_data)

    @action(detail=False, methods=['get'])
    def orders_by_location(self, request):
        """
        Get orders for specific location prefixes, including unknown locations
        """
        platform = request.query_params.get('platform', 'AMAZON')
        order_type = request.query_params.get('order_type', 'single')
        status = request.query_params.get('status', 'Ready to Process')
        location_prefixes = request.query_params.getlist('locations', [])  # Now expecting prefixes
        include_unknown = request.query_params.get('include_unknown', 'true').lower() == 'true'
        
        # Determine which model to use based on platform
        model_mapping = {
            'AMAZON': AmazonOrders,
            'FLIPKART': FlipkarOrders,
            'FIRSTCRY': FirstcryOrders,
            'MEESHO': MeeshoOrders
        }
        
        platform_upper = platform.upper()
        if platform_upper not in model_mapping:
            return Response({
                'error': f'Unknown platform: {platform}'
            }, status=400)
            
        order_model = model_mapping[platform_upper]
        
        # Filter by order type and status
        db_order_type = 'Single' if order_type.lower() == 'single' else 'Multiple'
        orders = order_model.objects.filter(
            order_type=db_order_type,
            status=status
        )
        
        # Find all full locations that match the selected prefixes
        matching_locations = []
        if location_prefixes:
            all_locations = MasterTable.objects.values_list('location', flat=True).distinct()
            for loc in all_locations:
                location_prefix = self._get_location_prefix(loc)
                if location_prefix in location_prefixes:
                    matching_locations.append(loc)
        
        # Find all SKUs in the matching locations
        skus_in_locations = MasterTable.objects.filter(
            location__in=matching_locations
        ).values_list('sku', flat=True).distinct()
        
        # Get all SKUs in orders
        all_order_skus = orders.values_list('sku', flat=True).distinct()
        
        # Get SKUs that exist in orders but not in MasterTable or with unknown locations
        if include_unknown:
            known_skus = MasterTable.objects.filter(
                sku__in=all_order_skus
            ).values_list('sku', flat=True).distinct()
            
            unknown_skus = set(all_order_skus) - set(known_skus)
        else:
            unknown_skus = set()
        
        # Filter orders to include those with SKUs in specified location prefixes or unknown locations
        if location_prefixes or include_unknown:
            # If location prefixes are specified or include_unknown is true
            filtered_orders = orders.filter(
                Q(sku__in=skus_in_locations) | Q(sku__in=unknown_skus)
            )
        else:
            # Include all orders if no filters are applied
            filtered_orders = orders
        
        # Prepare the response
        result = []
        for order in filtered_orders:
            # Get locations for this order's SKU if available
            sku_locations = MasterTable.objects.filter(sku=order.sku)
            location_info = []
            
            if sku_locations.exists():
                # SKU has known locations
                for loc in sku_locations:
                    location_prefix = self._get_location_prefix(loc.location)
                    location_info.append({
                        'location': loc.location,  # Full location
                        'location_prefix': location_prefix,  # Grouped prefix
                        'box_no': loc.box_no,
                        'selected': location_prefix in location_prefixes
                    })
            else:
                # SKU has unknown location
                location_info.append({
                    'location': "Unknown",
                    'location_prefix': "Unknown",
                    'box_no': "",
                    'selected': include_unknown
                })
            
            result.append({
                'order_number': order.order_number,
                'sku': order.sku,
                'quantity': order.quantity,
                'locations': location_info
            })
        
        # Sort by location prefix (prioritizing selected prefixes)
        def location_sort_key(order):
            # First sort by whether any location prefix is selected
            has_selected = any(loc['selected'] for loc in order['locations'])
            # Then by the first selected location prefix if any
            selected_prefix = next((loc['location_prefix'] for loc in order['locations'] if loc['selected']), "ZZZZZ")
            return (not has_selected, selected_prefix)
        
        result = sorted(result, key=location_sort_key)
        
        return Response(result)
    
    @action(detail=False, methods=['post'])
    def process_location_orders(self, request):
        """
        Process orders from specific location prefixes with batch and SKU limits
        """
        try:
            # Get data from request
            platform = request.data.get('platform', 'UNKNOWN').upper()
            order_type = request.data.get('order_type', 'SINGLE').upper()
            location_prefixes = request.data.get('locations', [])  # Now expecting prefixes
            include_unknown = request.data.get('include_unknown', True)
            batch_limit = request.data.get('batch_limit', 50)
            sku_limit = request.data.get('sku_limit', 0)
            next_status = request.data.get('next_status', 'Pick')
            
            # Validate inputs
            if not location_prefixes and not include_unknown:
                return Response({
                    'status': 'error',
                    'message': 'No location prefixes specified and unknown locations not included'
                }, status=400)
            
            # Convert limits to integers
            try:
                batch_limit = int(batch_limit)
                sku_limit = int(sku_limit)
            except (ValueError, TypeError) as e:
                batch_limit = 50
                sku_limit = 0
            
            # Determine the order model based on platform
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
            
            # Get orders for the specified location prefixes
            db_order_type = 'Single' if order_type == 'SINGLE' else 'Multiple'
            
            # Find all full locations that match the selected prefixes
            matching_locations = []
            if location_prefixes:
                all_locations = MasterTable.objects.values_list('location', flat=True).distinct()
                for loc in all_locations:
                    location_prefix = self._get_location_prefix(loc)
                    if location_prefix in location_prefixes:
                        matching_locations.append(loc)
            
            # Find all SKUs in the matching locations
            skus_in_locations = MasterTable.objects.filter(
                location__in=matching_locations
            ).values_list('sku', flat=True).distinct()
            
            # Get all SKUs in orders
            all_order_skus = order_model.objects.filter(
                order_type=db_order_type,
                status='Ready to Process'
            ).values_list('sku', flat=True).distinct()
            
            # Get SKUs that exist in orders but not in MasterTable
            if include_unknown:
                known_skus = MasterTable.objects.filter(
                    sku__in=all_order_skus
                ).values_list('sku', flat=True).distinct()
                
                unknown_skus = set(all_order_skus) - set(known_skus)
            else:
                unknown_skus = set()
            
            # Get orders with these SKUs
            orders = order_model.objects.filter(
                order_type=db_order_type,
                status='Ready to Process'
            ).filter(Q(sku__in=skus_in_locations) | Q(sku__in=unknown_skus))
            
            if not orders.exists():
                return Response({
                    'status': 'error',
                    'message': 'No orders found with the specified criteria',
                }, status=404)
            
            # Process orders in batches respecting both batch_limit and sku_limit
            processed_orders = []
            created_picklists = []
            
            all_orders = list(orders)
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
                    created_picklists.pop()
            
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
                'location_prefixes': location_prefixes,  # Updated field name
                'matching_full_locations': matching_locations,  # Show which full locations were included
                'include_unknown': include_unknown,
                'processed_orders': processed_orders,
                'picklist_ids': created_picklists,
                'main_picklist_id': created_picklists[0] if created_picklists else None
            })
        
        except Exception as e:
            import traceback
            print(f"Error in process_location_orders: {str(e)}")
            traceback.print_exc()
            
            return Response({
                'status': 'error',
                'message': f'Error processing orders: {str(e)}',
            }, status=500)