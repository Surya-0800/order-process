"""
Views for handling product image uploads and processing.
"""
import uuid
import os
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser

from ..models import ImageUpload  # Import the model after you create it
from ..serializers import (
    ImageUploadSerializer, 
    ImageUploadCreateSerializer, 
    ImageDetailSerializer
)  # Import serializers after you create them

class ImageUploadViewSet(viewsets.ModelViewSet):
    """
    ViewSet for handling image uploads, retrievals, and downloads.
    """
    queryset = ImageUpload.objects.all().order_by('-uploaded_at')
    parser_classes = (MultiPartParser, FormParser)
    
    def get_serializer_class(self):
        if self.action == 'create' or self.action == 'upload_multiple':
            return ImageUploadCreateSerializer
        elif self.action == 'retrieve':
            return ImageDetailSerializer
        return ImageUploadSerializer
    
    def create(self, request, *args, **kwargs):
        """Handle single image upload"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image = serializer.save()
        
        return Response(
            ImageUploadSerializer(image).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['post'])
    def upload_multiple(self, request):
        """Handle multiple image uploads"""
        files = request.FILES.getlist('images')
        title_prefix = request.data.get('title_prefix', '')
        
        if not files:
            return Response(
                {'error': 'No files provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_images = []
        for i, file in enumerate(files):
            serializer = ImageUploadCreateSerializer(data={
                'title': f"{title_prefix} {i+1}" if title_prefix else "",
                'image': file
            })
            
            if serializer.is_valid():
                image = serializer.save()
                uploaded_images.append(ImageUploadSerializer(image).data)
            else:
                # Skip invalid files but continue processing
                continue
        
        return Response(
            {'images': uploaded_images},
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download an image by its ID"""
        image = self.get_object()
        response = HttpResponse(image.image, content_type=image.content_type)
        response['Content-Disposition'] = f'attachment; filename="{image.file_name}"'
        return response
        
    @action(detail=False, methods=['post'])
    def process_folder(self, request):
        """
        Process a folder of images specified by path.
        This is a server-side implementation for bulk processing.
        """
        folder_path = request.data.get('folder_path')
        if not folder_path or not os.path.exists(folder_path):
            return Response(
                {'error': f'Invalid folder path: {folder_path}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get all image files from the folder
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        uploaded_images = []
        
        try:
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                file_ext = os.path.splitext(filename)[1].lower()
                
                # Skip if not a file or not an image file
                if not os.path.isfile(file_path) or file_ext not in valid_extensions:
                    continue
                
                # Read file content
                with open(file_path, 'rb') as file:
                    file_content = file.read()
                
                # Determine content type based on extension
                content_type_map = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp'
                }
                content_type = content_type_map.get(file_ext, 'application/octet-stream')
                
                # Create image record
                image = ImageUpload.objects.create(
                    title=os.path.splitext(filename)[0],
                    file_name=filename,
                    image=file_content,
                    content_type=content_type
                )
                
                uploaded_images.append(ImageUploadSerializer(image).data)
                
            return Response(
                {'images': uploaded_images},
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {'error': f'Error processing folder: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@csrf_exempt
def upload_multiple_images(request):
    """
    API endpoint to handle multiple image uploads.
    This is a function-based view that can be used alongside the ViewSet.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)
    
    files = request.FILES.getlist('images')
    title_prefix = request.POST.get('title_prefix', '')
    
    if not files:
        return JsonResponse({'error': 'No files provided'}, status=400)
    
    uploaded_images = []
    for i, file in enumerate(files):
        try:
            # Read the file content
            file_content = file.read()
            
            # Create and save the image upload
            image_upload = ImageUpload.objects.create(
                title=f"{title_prefix} {i+1}" if title_prefix else "",
                file_name=file.name,
                image=file_content,
                content_type=file.content_type
            )
            
            uploaded_images.append({
                'id': str(image_upload.id),
                'title': image_upload.title,
                'file_name': image_upload.file_name,
                'uploaded_at': image_upload.uploaded_at
            })
        except Exception as e:
            # Log the error and continue with other files
            print(f"Error uploading file {file.name}: {str(e)}")
            continue
    
    return JsonResponse({'images': uploaded_images}, status=201)

def upload_image_view(request):
    """
    View function to render the image uploader page
    """
    return render(request, 'product_images.html')