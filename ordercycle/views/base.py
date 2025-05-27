"""
Base views for the application.
Contains common views like home page, etc.
"""
from django.shortcuts import render

def home(request):
    """View for the home page."""
    return render(request, 'upload_pdf.html')

def image_processor_view(request):
    return render(request, 'product_images.html')

def location_orders_view(request):
    """View for the location-based order processing page."""
    return render(request, 'location_orders.html')
from django.http import Http404
from ..models import Picklist, Picker
def picklist_detail_view(request, picklist_id):
    """
    View to display picklist details page
    """
    try:
        # Get the picklist to extract platform information
        picklist = Picklist.objects.get(picklist_id=picklist_id)
        
        # Get all active pickers with names
        pickers = Picker.objects.filter(is_active=True).values('picker_id', 'name')
        
        context = {
            'picklist_id': picklist_id,
            'platform_name': picklist.platform,  # Add this line
            'pickers': list(pickers),
        }
        
        return render(request, 'picklist_detail.html', context)
        
    except Picklist.DoesNotExist:
        # Handle case where picklist doesn't exist
        context = {
            'picklist_id': picklist_id,
            'platform_name': 'Unknown Platform',  # Fallback
            'pickers': [],
            'error': 'Picklist not found'
        }
        return render(request, 'picklist_detail.html', context)

def pack_stage_view(request):
    """Render the packing stage page."""
    return render(request, 'pack_stage.html')

def picker_management(request):
    """Render the picker management page."""
    return render(request, 'picker_management.html')

def admin_dashboard_view(request):
    return render(request, 'admin_dashboard.html')