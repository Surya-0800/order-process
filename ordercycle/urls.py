"""
URL routing for the application.
"""
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from .views.base import (
    home, location_orders_view, picklist_detail_view, 
    pack_stage_view, picker_management
)
from .views.packing_views import (
    search_picklist, search_product, mark_picklist_completed,
    mark_product_packed, get_picklist_barcode, get_product_image_by_sku,save_awb_and_dispatch
)
from .views.printing_views import (
    get_printer_list, save_printer_preferences, get_printer_preferences,
    send_test_print, print_label, mark_order_as_printed, save_awb_number,
    print_invoice, search_awb
)
from .views.location_views import (
   LocationOrdersViewSet
)

from .views.proudct_images import (
    ImageUploadViewSet, 
    upload_image_view, 
    upload_multiple_images  
)

from .views.picklist_views import PicklistViewSet

from .views import dispatch_views as views
from .views.base import image_processor_view
from .views.pdf_upload import check_pdf_path

urlpatterns = [
    # Base views
    path('', home, name='home'),
    path('location-orders/', location_orders_view, name='location_orders'),

    # Add these URL patterns to your urlpatterns list
    path('image-upload/', upload_image_view, name='image_upload'),  # Template view for the image upload page

    # API endpoints for image uploads
    path('api/images/upload-multiple/', upload_multiple_images, name='upload_multiple_images'),

    # Additional image API endpoints if not already present
    path('api/images/', ImageUploadViewSet.as_view({'get': 'list', 'post': 'create'}), name='image-list'),
    path('api/images/<uuid:pk>/', ImageUploadViewSet.as_view({'get': 'retrieve', 'delete': 'destroy'}), name='image-detail'),
    path('api/images/<uuid:pk>/download/', ImageUploadViewSet.as_view({'get': 'download'}), name='image-download'),

    # If you want to process a whole folder at once (optional)
    path('api/images/process-folder/', ImageUploadViewSet.as_view({'post': 'process_folder'}), name='process-folder'),

    path('api/location-counts/', LocationOrdersViewSet.as_view({'get': 'location_counts'})),
    path('api/orders-by-location/', LocationOrdersViewSet.as_view({'get': 'orders_by_location'}), name='orders_by_location'),
    path('api/process-location-orders/', LocationOrdersViewSet.as_view({'post': 'process_location_orders'}), name='process_location_orders'),
    path('api/orders/save-awb/', save_awb_and_dispatch, name='save_awb_and_dispatch'),
    # Picklist detail views - both URL patterns point to the same view function
    path('picklist/<str:picklist_id>/', picklist_detail_view, name='picklist_detail'),
    path('picklist-details/<str:picklist_id>/', picklist_detail_view, name='picklist_details'),
    
    path('pack-stage/', pack_stage_view, name='pack_stage'),
    path('picker-management/', picker_management, name='picker_management'),
    
    # Packing views
    path('api/search-picklist/', search_picklist, name='search_picklist'),
    # Add this line to fix the 404 error
    path('api/picklists/search/', search_picklist, name='picklists_search'),
    path('api/picklists/<str:pk>/delete-picklist/', PicklistViewSet.as_view({'delete': 'delete_picklist'}), name='delete_picklist'),
    path('api/picklists/delete-bulk/', PicklistViewSet.as_view({'post': 'delete_picklists'}),name="delete_bulk_picklists"),
    
    path('api/search-product/', search_product, name='search_product'),
    path('api/picklist/<str:picklist_id>/complete/', mark_picklist_completed, name='mark_picklist_completed'),
    path('api/mark-product-packed/', mark_product_packed, name='mark_product_packed'),
    path('api/picklist/<str:picklist_id>/barcode/', get_picklist_barcode, name='get_picklist_barcode'),
    path('api/product-image-by-sku/', get_product_image_by_sku, name='get_product_image_by_sku'),
    path('api/products/image-by-sku/', get_product_image_by_sku, name='products_image_by_sku'),
    
    # Printing views
    path('api/printer/list/', get_printer_list, name='get_printer_list'),
    path('api/printer/save-preferences/', save_printer_preferences, name='save_printer_preferences'),
    path('api/printer/get-preferences/', get_printer_preferences, name='get_printer_preferences'),
    path('api/printer/test-print/', send_test_print, name='send_test_print'),
    path('api/print-label/', print_label, name='print_label'),
    path('api/mark-order-printed/', mark_order_as_printed, name='mark_order_as_printed'),
    path('api/orders/mark-printed/', mark_order_as_printed, name='mark_order_as_printed'),
    path('api/print-invoice/', print_invoice, name='print_invoice'),
    path('api/search-awb/', search_awb, name='search_awb'),

    path('api/picklists/dispatch/', views.get_dispatch_picklists, name='get_dispatch_picklists'),
    path('api/picklists/<str:picklist_id>/dispatch-orders/', views.get_dispatch_orders, name='get_dispatch_orders'),
    path('api/picklists/<str:picklist_id>/mark-dispatched/', views.mark_orders_as_dispatched, name='mark_orders_as_dispatched'),
    
    # Include API routes - make sure this comes after individual API routes
    path('api/', include('ordercycle.api.urls')),

    path('api/search-dispatch-awb/', views.search_by_awb, name='search_by_awb'),
    path('api/orders/complete-by-awb/', views.complete_orders_by_awb, name='complete_orders_by_awb'),

    path('api/orders/change-to-dispatch/', views.change_to_dispatch, name='change-to-dispatch'),
    path('api/orders/bulk-change-to-dispatch/', views.bulk_change_to_dispatch, name='bulk-change-to-dispatch'),

    path('api/check-pdf-path/', check_pdf_path, name='check_pdf_path')
]

# Add media URL patterns for development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)