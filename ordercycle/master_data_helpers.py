# yourapp/master_data_helpers.py
from django.db.models import Q
from .models import MasterTable  # Updated to use MasterTable

def get_item_by_sku_location(sku, location):
    """
    Get a specific item by SKU and location
    """
    try:
        return MasterTable.objects.get(sku=sku, location=location)
    except MasterTable.DoesNotExist:
        return None

def get_all_locations_for_sku(sku):
    """
    Get all locations where a specific SKU is stored
    """
    return MasterTable.objects.filter(sku=sku).values('location', 'box_no')

def get_item_by_product_id(product_id):
    """
    Get items by product ID
    """
    return MasterTable.objects.filter(product_id=product_id)

def get_items_by_box(box_no):
    """
    Get all items in a specific box
    """
    return MasterTable.objects.filter(box_no=box_no)

def get_items_in_location(location):
    """
    Get all items in a specific location
    """
    return MasterTable.objects.filter(location=location).order_by('sku')

def search_items(query):
    """
    Search for items by SKU, generic name, or location
    """
    if not query:
        return []
        
    return MasterTable.objects.filter(
        Q(sku__icontains=query) |
        Q(generic_name__icontains=query) |
        Q(location__icontains=query) |
        Q(product_id__icontains=query)
    ).order_by('sku')

def get_highest_mrp_items(limit=50):
    """
    Get items with the highest MRP
    """
    return MasterTable.objects.all().order_by('-mrp')[:limit]

def get_pack_check_status(sku, location=None):
    """
    Get pack check status for an item
    """
    query = MasterTable.objects.filter(sku=sku)
    if location:
        query = query.filter(location=location)
    
    items = query.values('pack_check', 'pack_remarks')
    return list(items)

def get_sorted_items_by_sku(descending=True):
    """
    Get all items sorted by SKU (descending by default)
    """
    if descending:
        return MasterTable.objects.all().order_by('-sku')
    return MasterTable.objects.all().order_by('sku')

def get_image_url(sku, location=None):
    """
    Get the image URL for a specific SKU
    """
    query = MasterTable.objects.filter(sku=sku)
    if location:
        query = query.filter(location=location)
        
    item = query.first()
    return item.image_url if item else None