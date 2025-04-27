"""
Base views for the application.
Contains common views like home page, etc.
"""
from django.shortcuts import render

def home(request):
    """View for the home page."""
    return render(request, 'upload_pdf.html')

def location_orders_view(request):
    """View for the location-based order processing page."""
    return render(request, 'location_orders.html')

def picklist_detail_view(request, picklist_id):
    """
    Render the picklist details page with barcode capabilities.
    """
    from django.http import Http404
    from ..models import Picklist, Picker
    
    try:
        # Check if picklist exists
        picklist = Picklist.objects.get(picklist_id=picklist_id)
        
        # Get all active pickers
        pickers = Picker.objects.filter(is_active=True)
        
        context = {
            'picklist_id': picklist_id,
            'pickers': pickers,
            # Add barcode library CSS/JS resources to template context
            'include_barcode_library': True,
        }
        
        return render(request, 'picklist_detail.html', context)
    except Picklist.DoesNotExist:
        raise Http404("Picklist does not exist")

def pack_stage_view(request):
    """Render the packing stage page."""
    return render(request, 'pack_stage.html')

def picker_management(request):
    """Render the picker management page."""
    return render(request, 'picker_management.html')