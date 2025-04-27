"""
Utility functions for printing operations.
"""
import os
import fitz  # PyMuPDF
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site

def get_pdf_url_for_order(order, platform, request=None):
    """
    Get the PDF URL for an order.
    
    Args:
        order: Order object with pdf_url attribute
        platform (str): Platform name (AMAZON, FLIPKART, etc.)
        request: HTTP request object for building absolute URLs
        
    Returns:
        dict: Dictionary containing URL and file information
    """
    from .file_utils import get_platform_directory, copy_file_to_media, find_file_in_media_root
    
    pdf_path = order.pdf_url
    if not pdf_path:
        return {
            'status': 'error',
            'message': 'No PDF file found for this order'
        }
    
    # Variables to track paths and URLs
    actual_file_path = None
    pdf_url = None
    
    # Case 1: If it's a full file system path (Windows or Unix)
    if pdf_path.startswith('C:') or pdf_path.startswith('/'):
        # Get just the filename from the path
        filename = os.path.basename(pdf_path)
        
        # Determine platform directory
        platform_dir = get_platform_directory(platform)
        
        # Construct media URL
        platform_upper = platform.upper()
        platform_dir_mapping = {
            'AMAZON': 'amazonPdfs',
            'FLIPKART': 'flipkartPdfs',
            'FIRSTCRY': 'firstcryPdfs',
            'MEESHO': 'meeshoPdfs',
        }
        pdf_url = f"media/{platform_dir_mapping.get(platform_upper, 'orderPdfs')}/{filename}"
        
        # Construct media path
        media_path = os.path.join(platform_dir, filename)
        
        # Check if file exists in media directory
        if not os.path.exists(media_path):
            # Try to copy the file
            if os.path.exists(pdf_path):
                # Source file exists, copy it
                dest_path, success = copy_file_to_media(pdf_path, platform)
                if success:
                    actual_file_path = dest_path
                else:
                    # Copy failed
                    return {
                        'status': 'error',
                        'message': f'Failed to copy PDF file to media directory'
                    }
            else:
                # Source file doesn't exist, try to find it elsewhere
                alternate_path = find_file_in_media_root(filename)
                if alternate_path:
                    # Found file in media directory
                    actual_file_path = alternate_path
                    
                    # Adjust PDF URL based on the found location
                    rel_path = os.path.relpath(alternate_path, settings.MEDIA_ROOT)
                    pdf_url = f"media/{rel_path.replace(os.path.sep, '/')}"
                else:
                    # File not found anywhere
                    return {
                        'status': 'error',
                        'message': f'PDF file not found'
                    }
        else:
            # File already exists in the media directory
            actual_file_path = media_path
    
    # Case 2: It's already a relative URL path
    else:
        pdf_url = pdf_path
        
        # Ensure it starts with media/ for URLs
        if not pdf_url.startswith('media/') and not pdf_url.startswith('/media/'):
            pdf_url = f"media/{pdf_url.lstrip('/')}"
        
        # Try to determine the file path from the URL
        if pdf_url.startswith('/media/'):
            path_part = pdf_url.lstrip('/media/')
        else:
            path_part = pdf_url.lstrip('media/')
            
        possible_path = os.path.join(settings.MEDIA_ROOT, path_part)
        if os.path.exists(possible_path):
            actual_file_path = possible_path
    
    # Ensure pdf_url starts with / for URL construction
    if not pdf_url.startswith('/'):
        pdf_url = f"/{pdf_url}"
    
    # Build the response
    result = {
        'status': 'success',
        'pdf_url': pdf_url,
        'actual_file_path': actual_file_path,
        'file_exists': actual_file_path and os.path.exists(actual_file_path)
    }
    
    # Add absolute URL if request is provided
    if request:
        protocol = 'https' if request.is_secure() else 'http'
        domain = get_current_site(request).domain
        result['absolute_url'] = f"{protocol}://{domain}{pdf_url}"
    
    return result

def get_label_page_index(pdf_path, platform):
    """
    Determine the page index of the shipping label in a PDF.
    
    Args:
        pdf_path (str): Path to the PDF file
        platform (str): Platform name (AMAZON, FLIPKART, etc.)
        
    Returns:
        int: Page index of the shipping label (0-based)
    """
    platform_upper = platform.upper()
    
    # Default label position by platform
    if platform_upper == 'FIRSTCRY':
        # For FirstCry, check if label is the last page
        try:
            # Normalize the path if needed
            if pdf_path.startswith('/media/'):
                pdf_path = os.path.join(settings.MEDIA_ROOT, pdf_path.lstrip('/media/'))
            
            # Open the PDF and get page count
            pdf_document = fitz.open(pdf_path)
            page_count = len(pdf_document)
            
            # For FirstCry, the label is usually the last page
            label_page_index = page_count - 1
            pdf_document.close()
            return label_page_index
        except Exception as e:
            print(f"Error determining label page: {e}")
            return 0  # Default to first page on error
    
    # For all other platforms, default to first page
    return 0