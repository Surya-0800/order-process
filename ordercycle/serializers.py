from rest_framework import serializers
from .models import PDFUpload,ImageUpload

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

from rest_framework import serializers
from .models import ImageUpload
import base64

class ImageUploadSerializer(serializers.ModelSerializer):
    """
    Serializer for listing and retrieving image uploads (without binary data).
    """
    class Meta:
        model = ImageUpload
        fields = ['id', 'title', 'file_name', 'content_type', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

class ImageUploadCreateSerializer(serializers.Serializer):
    """
    Serializer for creating new image uploads.
    """
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    image = serializers.FileField()
    
    def create(self, validated_data):
        image_file = validated_data.get('image')
        title = validated_data.get('title', '')
        
        # Read the file content
        file_content = image_file.read()
        
        # Create and save the image upload
        image_upload = ImageUpload.objects.create(
            title=title,
            file_name=image_file.name,
            image=file_content,
            content_type=image_file.content_type
        )
        
        return image_upload

class ImageDetailSerializer(ImageUploadSerializer):
    """
    Serializer for retrieving image upload details including the encoded image data.
    """
    image_data = serializers.SerializerMethodField()
    
    class Meta(ImageUploadSerializer.Meta):
        fields = ImageUploadSerializer.Meta.fields + ['image_data']
    
    def get_image_data(self, obj):
        """
        Return the image data as base64 encoded string.
        """
        return base64.b64encode(obj.image).decode('utf-8')