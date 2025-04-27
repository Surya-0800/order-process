from rest_framework import serializers
from .models import PDFUpload

class PDFUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PDFUpload
        fields = '__all__'

from rest_framework import serializers
from .models import Picker

class PickerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Picker
        fields = ['id', 'picker_id', 'name', 'is_active']