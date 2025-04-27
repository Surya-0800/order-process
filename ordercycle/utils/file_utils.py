"""
Utility functions for file handling.
"""
import os
import shutil
from django.conf import settings

def ensure_directory_exists(directory_path):
    """
    Ensure a directory exists, create it if it doesn't.
    
    Args:
        directory_path (str): Path to the directory
    """
    os.makedirs(directory_path, exist_ok=True)

def get_platform_directory(platform):
    """
    Get the appropriate media directory for a platform.
    
    Args:
        platform (str): Platform name (AMAZON, FLIPKART, etc.)
        
    Returns:
        str: Path to the platform's media directory
    """
    platform_upper = platform.upper()
    platform_dir_mapping = {
        'AMAZON': 'amazonPdfs',
        'FLIPKART': 'flipkartPdfs',
        'FIRSTCRY': 'firstcryPdfs',
        'MEESHO': 'meeshoPdfs',
    }
    
    directory_name = platform_dir_mapping.get(platform_upper, 'orderPdfs')
    directory_path = os.path.join(settings.MEDIA_ROOT, directory_name)
    
    # Ensure the directory exists
    ensure_directory_exists(directory_path)
    
    return directory_path

def copy_file_to_media(source_path, platform):
    """
    Copy a file to the appropriate media directory for a platform.
    
    Args:
        source_path (str): Path to the source file
        platform (str): Platform name (AMAZON, FLIPKART, etc.)
        
    Returns:
        str: Path to the copied file
        bool: Whether the copy was successful
    """
    if not os.path.exists(source_path):
        return None, False
    
    # Get the destination directory
    dest_dir = get_platform_directory(platform)
    
    # Get just the filename
    filename = os.path.basename(source_path)
    
    # Construct the destination path
    dest_path = os.path.join(dest_dir, filename)
    
    # Copy the file
    try:
        shutil.copy2(source_path, dest_path)
        success = os.path.exists(dest_path)
    except Exception as e:
        print(f"Error copying file: {e}")
        success = False
    
    return dest_path if success else None, success

def find_file_in_media_root(filename):
    """
    Find a file in the media root directory or its subdirectories.
    
    Args:
        filename (str): Name of the file to find
        
    Returns:
        str: Path to the file if found, None otherwise
    """
    for root, dirs, files in os.walk(settings.MEDIA_ROOT):
        if filename in files:
            return os.path.join(root, filename)
    
    return None