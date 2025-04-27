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
    mark_product_packed, get_picklist_barcode, get_product_image_by_sku
)
from .views.printing_views import (
    get_printer_list, save_printer_preferences, get_printer_preferences,
    send_test_print, print_label, mark_order_as_printed, save_awb_number,
    print_invoice, search_awb
)

urlpatterns = [
    # Base views
    path('', home, name='home'),
    path('location-orders/', location_orders_view, name='location_orders'),
    path('picklist/<str:picklist_id>/', picklist_detail_view, name='picklist_detail'),
    path('pack-stage/', pack_stage_view, name='pack_stage'),
    path('picker-management/', picker_management, name='picker_management'),
    
    # Packing views
    path('api/search-picklist/', search_picklist, name='search_picklist'),
    path('api/search-product/', search_product, name='search_product'),
    path('api/picklist/<str:picklist_id>/complete/', mark_picklist_completed, name='mark_picklist_completed'),
    path('api/mark-product-packed/', mark_product_packed, name='mark_product_packed'),
    path('api/picklist/<str:picklist_id>/barcode/', get_picklist_barcode, name='get_picklist_barcode'),
    path('api/product-image-by-sku/', get_product_image_by_sku, name='get_product_image_by_sku'),
    
    # Printing views
    path('api/printer/list/', get_printer_list, name='get_printer_list'),
    path('api/printer/save-preferences/', save_printer_preferences, name='save_printer_preferences'),
    path('api/printer/get-preferences/', get_printer_preferences, name='get_printer_preferences'),
    path('api/printer/test-print/', send_test_print, name='send_test_print'),
    path('api/print-label/', print_label, name='print_label'),
    path('api/mark-order-printed/', mark_order_as_printed, name='mark_order_as_printed'),
    path('api/save-awb/', save_awb_number, name='save_awb_number'),
    path('api/print-invoice/', print_invoice, name='print_invoice'),
    path('api/search-awb/', search_awb, name='search_awb'),
    
    # API routes
    path('api/', include('app.api.urls')),
]

# Add media URL patterns for development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)