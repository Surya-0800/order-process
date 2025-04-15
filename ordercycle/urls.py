from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.conf import settings
from django.conf.urls.static import static
from .views import (
    PDFUploadViewSet, OrderCountsViewSet,LocationOrdersViewSet,
    PicklistViewSet, home, picklist_detail_view, 
    get_picklist_barcode, pack_stage_view, search_picklist,
    search_product, mark_product_packed, mark_picklist_completed,print_order_label,search_awb, get_printer_list, save_printer_preferences, 
    get_printer_preferences, send_test_print,location_orders_view
)

# API Router
router = DefaultRouter()
router.register(r'pdfs', PDFUploadViewSet, basename='pdfupload')

# URL Configuration
urlpatterns = [
    path('', home, name='home'),
    path('api/', include(router.urls)),
    
    # Packing Stage endpoints - place these FIRST
    path('pack/', pack_stage_view, name='pack-stage'),
    # Note: URL patterns are processed in order, so put specific patterns before patterns with variables
    path('api/picklists/search/', search_picklist, name='search-picklist'),
    path('api/products/search/', search_product, name='search-product'),
    path('api/products/mark-packed/', mark_product_packed, name='mark-product-packed'),
    path('api/picklists/<str:picklist_id>/complete/', mark_picklist_completed, name='mark-picklist-completed'),
    
    # New endpoint for direct file processing
    path('api/process-files/', PDFUploadViewSet.as_view({'post': 'process_files'}), name='process-files'),
    
    # Legacy endpoint - keep it for backward compatibility
    path('api/read-pdfs/', PDFUploadViewSet.as_view({'get': 'read_pdfs'}), name='read-pdfs'),
    
    # Order counts and processing endpoints
    path('api/order-counts/', OrderCountsViewSet.as_view({'get': 'get_counts'}), name='order-counts'),
    path('api/single-orders/', OrderCountsViewSet.as_view({'get': 'get_single_orders'}), name='single-orders'),
    path('api/multi-orders/', OrderCountsViewSet.as_view({'get': 'get_multi_orders'}), name='multi-orders'),
    path('api/process-orders/', OrderCountsViewSet.as_view({'post': 'process_orders'}), name='process-orders'),
    
    # Picklist endpoints - more specific patterns first, then patterns with variables
    path('api/picklists/', PicklistViewSet.as_view({'get': 'get_picklists'}), name='picklists'),
    path('api/picklists/<str:pk>/', PicklistViewSet.as_view({'get': 'get_picklist_items'}), name='picklist-detail'),
    path('api/picklists/<str:pk>/status/', PicklistViewSet.as_view({'post': 'update_status'}), name='picklist-status-update'),
    path('api/picklists/<str:pk>/update-status/', PicklistViewSet.as_view({'post': 'update_status'}), name='picklist-update-status'),
    path('api/picklists/<str:pk>/detailed-items/', PicklistViewSet.as_view({'get': 'get_detailed_items'}), name='picklist-detailed-items'),
    path('api/picklists/<str:pk>/undo-picked/', PicklistViewSet.as_view({'post': 'undo_picked'}), name='undo-picked'),
    path('api/picklists/<str:pk>/assign-picker/', PicklistViewSet.as_view({'post': 'assign_picker'}), name='assign-picker'),
    path('api/picklists/<str:pk>/mark-picked/', PicklistViewSet.as_view({'post': 'mark_picked'}), name='mark-picked'),
    path('api/picklists/<str:pk>/mark-items-picked/', PicklistViewSet.as_view({'post': 'mark_items_picked'}), name='mark-items-picked'),
    path('api/picklists/<str:picklist_id>/barcode/', get_picklist_barcode, name='picklist-barcode'),
    path('api/print-label/', print_order_label, name='print-label'),
    path('api/search-awb/', search_awb, name='search-awb'),
    path('api/printers/', get_printer_list, name='get-printers'),
    path('api/printers/preferences/', get_printer_preferences, name='get-printer-preferences'),
    path('api/printers/preferences/save/', save_printer_preferences, name='save-printer-preferences'),
    path('api/printers/test-print/', send_test_print, name='send-test-print'),


    path('api/location-counts/', LocationOrdersViewSet.as_view({'get': 'location_counts'}), name='location-counts'),
    path('api/orders-by-location/', LocationOrdersViewSet.as_view({'get': 'orders_by_location'}), name='orders-by-location'),
    path('api/process-location-orders/', LocationOrdersViewSet.as_view({'post': 'process_location_orders'}), name='process-location-orders'),
    path('location-orders/', location_orders_view, name='location-orders'),
    
    # Detail view - must be after all API endpoints
    path('picklist-details/<str:picklist_id>/', picklist_detail_view, name='picklist-detail'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)