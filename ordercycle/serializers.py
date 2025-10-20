from rest_framework import serializers
from pathlib import Path
from django.conf import settings
from .models import PDFUpload, ImageUpload, Picker


class PDFUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PDFUpload
        fields = '__all__'


class PickerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Picker
        fields = ['id', 'picker_id', 'name', 'is_active']


class ImageUploadSerializer(serializers.ModelSerializer):
    """
    Serializer for listing and retrieving image uploads (metadata only, no binary data).
    Returns image URL instead of binary data for frontend consumption.
    """
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ImageUpload
        fields = ['id', 'title', 'file_name', 'content_type', 'uploaded_at', 'image_url']
        read_only_fields = ['id', 'uploaded_at']
    
    def get_image_url(self, obj):
        """
        Return the URL to access the image from the file system.
        This is fast because it only constructs a URL, no data transfer.
        """
        return f"{settings.MEDIA_URL}product_images/{obj.file_name}"


class ImageUploadCreateSerializer(serializers.Serializer):
    """
    Optimized serializer for creating new image uploads.
    Saves images to file system only, not to database binary field.
    Replaces existing images with the same filename.
    """
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    image = serializers.FileField()
    
    def create(self, validated_data):
        image_file = validated_data.get('image')
        title = validated_data.get('title', '')
        
        product_images_dir = Path(settings.MEDIA_ROOT) / 'product_images'
        product_images_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = product_images_dir / image_file.name
        
        # Delete existing database records with same filename to prevent orphaned records
        existing_images = ImageUpload.objects.filter(file_name=image_file.name)
        if existing_images.exists():
            existing_images.delete()
        
        # Save file to disk (will overwrite existing file if it exists)
        with open(file_path, 'wb') as destination:
            for chunk in image_file.chunks():
                destination.write(chunk)
        
        # Create new database record
        image_upload = ImageUpload.objects.create(
            title=title,
            file_name=image_file.name,
            content_type=image_file.content_type
        )
        
        return image_upload


class ImageDetailSerializer(ImageUploadSerializer):
    """
    Serializer for retrieving detailed image upload information.
    Returns file system URL instead of base64 encoded data for performance.
    """
    class Meta(ImageUploadSerializer.Meta):
        fields = ImageUploadSerializer.Meta.fields