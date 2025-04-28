"""
URL routing for API endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .viewsets import (
    PDFUploadViewSet,
    OrderCountsViewSet,
    PicklistViewSet,
    LocationOrdersViewSet,
    PickerViewSet,
)

# Initialize the router
router = DefaultRouter()

# Register ViewSets
router.register(r'pdf-uploads', PDFUploadViewSet, basename='pdf-upload')
router.register(r'order-counts', OrderCountsViewSet, basename='order-counts')
router.register(r'picklists', PicklistViewSet, basename='picklist')
router.register(r'location-orders', LocationOrdersViewSet, basename='location-orders')
router.register(r'pickers', PickerViewSet, basename='picker')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),

    path('picklists/<str:pk>/mark-picked/', 
         PicklistViewSet.as_view({'post': 'mark_picked'}), 
         name='picklist-mark-picked'),
         
    path('picklists/<str:pk>/mark-items-picked/', 
         PicklistViewSet.as_view({'post': 'mark_items_picked'}), 
         name='picklist-mark-items-picked'),
         
    path('picklists/<str:pk>/undo-picked/', 
         PicklistViewSet.as_view({'post': 'undo_picked'}), 
         name='picklist-undo-picked'),
         
    path('picklists/<str:pk>/update-status/', 
         PicklistViewSet.as_view({'post': 'update_status'}), 
         name='picklist-update-status'),
         
    path('picklists/<str:pk>/assign-picker/', 
         PicklistViewSet.as_view({'post': 'assign_picker'}), 
         name='picklist-assign-picker'),

     path('single-orders/', 
         OrderCountsViewSet.as_view({'get': 'get_single_orders'}), 
         name='single-orders'),

    path('multi-orders/', 
         OrderCountsViewSet.as_view({'get': 'get_multi_orders'}), 
         name='multi-orders'),
]