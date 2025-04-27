"""
Views for picker management functionality.
"""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models import Picker
from ..api.serializers import PickerSerializer

class PickerViewSet(viewsets.ModelViewSet):
    """
    A viewset that provides CRUD operations for Picker model.
    """
    queryset = Picker.objects.all()
    serializer_class = PickerSerializer
    
    @action(detail=True, methods=['patch'])
    def toggle_active(self, request, pk=None):
        """Toggle a picker's active status."""
        picker = self.get_object()
        picker.is_active = not picker.is_active
        picker.save()
        serializer = self.get_serializer(picker)
        return Response(serializer.data)