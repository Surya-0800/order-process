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

from rest_framework import serializers
from django.core.files.uploadedfile import UploadedFile

class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    
    def validate_file(self, value):
        if not value.name.endswith(('.xlsx', '.xls')):
            raise serializers.ValidationError("Only Excel files (.xlsx, .xls) are allowed.")
        
        # Check file size (limit to 10MB)
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("File size should not exceed 10MB.")
        
        return value

class ImportResultSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField()
    created_count = serializers.IntegerField()
    updated_count = serializers.IntegerField()
    skipped_count = serializers.IntegerField()
    error_count = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.CharField(), required=False)