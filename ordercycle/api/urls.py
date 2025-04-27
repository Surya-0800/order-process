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
]