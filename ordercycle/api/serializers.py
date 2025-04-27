"""
Serializers for API data conversion.
"""
from rest_framework import serializers
from ..models import PDFUpload, Picker

class PDFUploadSerializer(serializers.ModelSerializer):
    """Serializer for PDF uploads."""
    class Meta:
        model = PDFUpload
        fields = ('id', 'title', 'file', 'uploaded_at')

class PickerSerializer(serializers.ModelSerializer):
    """Serializer for Picker model."""
    class Meta:
        model = Picker
        fields = ('picker_id', 'name', 'is_active')