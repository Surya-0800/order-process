"""
Utility functions for PDF processing.
"""
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
import re

def clean_text(text):
    """Clean text by removing extra spaces, newlines, etc."""
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)  # Remove non-ASCII characters
    text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace
    text = text.replace("—", "-")  # Replace OCR misrecognized dashes
    return text

def extract_text_from_first_page(pdf_path, ocr=False):
    """Extract text only from the first page of a PDF."""
    doc = fitz.open(pdf_path)
    first_page = doc[0]  # Get first page
    text = first_page.get_text("text")
    
    if not text.strip():
        # Convert first page to image and apply OCR
        image = convert_from_path(pdf_path, first_page=1, last_page=1)[0]
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(image, config=custom_config)
    
    return clean_text(text)