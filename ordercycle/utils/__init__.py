"""
Utility functions for the application.
"""
from .pdf_helpers import extract_text_from_first_page
from .file_utils import ensure_directory_exists, get_platform_directory, copy_file_to_media, find_file_in_media_root
from .printing_utils import get_pdf_url_for_order, get_label_page_index