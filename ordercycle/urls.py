"""
URL routing for the application.
"""
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from .views.base import (
    home, location_orders_view, picklist_detail_view, 
    pack_stage_view, picker_management,admin_dashboard_view
)
from .views.packing_views import (
    search_picklist, search_product, mark_picklist_completed,
    mark_product_packed, get_picklist_barcode, get_product_image_by_sku,save_awb_and_dispatch,
    validate_sku, get_validation_status
)
from .views.printing_views import (
    get_printer_list, save_printer_preferences, get_printer_preferences,
    send_test_print, print_label, mark_order_as_printed, save_awb_number,
    print_invoice, search_awb,download_pdf,get_pending_print_jobs,mark_multiple_orders_printed
)
from .views.location_views import (
   LocationOrdersViewSet
)

from .views.proudct_images import (
    ImageUploadViewSet, 
    upload_image_view, 
    upload_multiple_images  
)

from .views.master_data import (
    import_master_data_api, 
    master_data_dashboard, 
    import_master_data_ajax  
)

from .views.picklist_views import PicklistViewSet

from .views import dispatch_views as views
from .views.base import image_processor_view
from .views.pdf_upload import check_pdf_path
from .views.order_management import (
    order_management_view, 
    search_order_api, 
    search_picklist_api,
    process_order_api, 
    process_picklist_api,
    mark_order_complete_api,
    get_order_status_api,
    validate_admin_password_api,
    process_selected_orders_api
)
urlpatterns = [
    # Base views
    path('', home, name='home'),

    path('api/orders/mark-complete/',mark_order_complete_api, name='mark_order_complete_api'),
    path('api/orders/status/', get_order_status_api, name='get_order_status_api'),

    path('admin-dashboard/', admin_dashboard_view, name='admin_dashboard'),

    path('api/import-master-data/', import_master_data_api, name='import_master_data_api'),
    
    # Dashboard
    path('dashboard/master-data/', master_data_dashboard, name='master_data_dashboard'),
    path('ajax/import-master-data/', import_master_data_ajax, name='import_master_data_ajax'),

    path('location-orders/', location_orders_view, name='location_orders'),

    # Add these URL patterns to your urlpatterns list
    path('image-upload/', upload_image_view, name='image_upload'),  # Template view for the image upload page
    path('api/print-jobs/pending/', get_pending_print_jobs, name='get_pending_print_jobs'),
    path('api/orders/mark-multiple-printed/', mark_multiple_orders_printed, name='mark_multiple_orders_printed'),

    # API endpoints for image uploads
    path('api/images/upload-multiple/', upload_multiple_images, name='upload_multiple_images'),

    # Additional image API endpoints if not already present
    path('api/images/', ImageUploadViewSet.as_view({'get': 'list', 'post': 'create'}), name='image-list'),
    path('api/images/<uuid:pk>/', ImageUploadViewSet.as_view({'get': 'retrieve', 'delete': 'destroy'}), name='image-detail'),
    path('api/images/<uuid:pk>/download/', ImageUploadViewSet.as_view({'get': 'download'}), name='image-download'),

    # If you want to process a whole folder at once (optional)
    path('api/images/process-folder/', ImageUploadViewSet.as_view({'post': 'process_folder'}), name='process-folder'),

    path('api/validate-sku/', validate_sku, name='validate_sku'),
    path('api/validation-status/', get_validation_status, name='get_validation_status'),

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

    path('api/dispatch/analytics/', views.get_dispatch_analytics_by_date, name='dispatch_analytics_by_date'),
    path('api/dispatch/statistics/', views.get_date_range_statistics, name='date_range_statistics'),

    path('api/picklists/<str:picklist_id>/download-csv-and-cleanup/', views.download_dispatch_csv_and_cleanup, name='download_csv_cleanup'),
    
    # Include API routes - make sure this comes after individual API routes
    path('api/', include('ordercycle.api.urls')),
    path('api/orders/mark-multiple-printed/', mark_multiple_orders_printed, name='mark_multiple_orders_printed'),

    path('api/search-dispatch-awb/', views.search_by_awb, name='search_by_awb'),
    path('api/orders/complete-by-awb/', views.complete_orders_by_awb, name='complete_orders_by_awb'),

    path('api/validate-password/', validate_admin_password_api, name='validate_admin_password_api'),

    # Process selected orders API  
    path('api/picklists/process-selected/', process_selected_orders_api, name='process_selected_orders_api'),

    path('api/orders/change-to-dispatch/', views.change_to_dispatch, name='change-to-dispatch'),
    path('api/orders/bulk-change-to-dispatch/', views.bulk_change_to_dispatch, name='bulk-change-to-dispatch'),
    path('api/picklists/<str:picklist_id>/check-fully-dispatched/', views.check_picklist_fully_dispatched, name='check_picklist_fully_dispatched'),
    path('api/picklists/<str:picklist_id>/download-csv-and-cleanup/', views.download_dispatch_csv_and_cleanup, name='download_dispatch_csv_and_cleanup'),

    path('api/check-pdf-path/', check_pdf_path, name='check_pdf_path'),
    path('api/orders/<str:order_id>/download/', download_pdf, name='order_pdf_download'),

    path('order-management/', order_management_view, name='order_management'),
    
    # Search APIs
    path('api/orders/search/', search_order_api, name='search_order_api'),
    path('api/search_picklists/<str:picklist_id>/', search_picklist_api, name='search_picklist_api'),
    
    # Processing APIs  
    path('api/orders/process/', process_order_api, name='process_order_api'),
    path('api/picklists/process/', process_picklist_api, name='process_picklist_api'),


]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)