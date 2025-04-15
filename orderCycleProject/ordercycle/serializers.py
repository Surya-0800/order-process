from rest_framework import serializers
from .models import PDFUpload

class PDFUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PDFUpload
        fields = '__all__'
