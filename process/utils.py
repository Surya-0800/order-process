import os
import re
import logging
import numpy as np
import fitz  # PyMuPDF
import cv2
import pyzbar.pyzbar as pyzbar
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import pandas as pd

def clean_text(text):
    """Clean text by removing extra spaces, newlines, etc."""
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)  # Remove non-ASCII characters
    text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace
    text = text.replace("—", "-")  # Replace OCR misrecognized dashes
    return text

def extract_text_from_page(page, pdf_path, ocr=False, poppler_path=r"C:\poppler\poppler-24.08.0\Library\bin"):
    """Extract text using PyMuPDF or OCR if necessary."""
    poppler_path=r"C:\poppler\poppler-24.08.0\Library\bin"
    text = page.get_text("text")
    if not text.strip() and ocr:
        # Convert page to image and apply OCR
        pix = page.get_pixmap()
        
        # Prepare poppler arguments
        poppler_kwargs = {
            'first_page': page.number+1,
            'last_page': page.number+1
        }
        if poppler_path:
            poppler_kwargs['poppler_path'] = poppler_path
            
        image = convert_from_path(pdf_path, **poppler_kwargs)[0]
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(image, config=custom_config)
    return clean_text(text)

def extract_text_from_first_page(pdf_path, ocr=False, poppler_path=None):
    """Extract text from the first page of a PDF for platform identification."""
    poppler_path=r"C:\poppler\poppler-24.08.0\Library\bin"
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count > 0:
            return extract_text_from_page(doc[0], pdf_path, ocr, poppler_path)
    except Exception as e:
        logging.error(f"Error extracting text from first page: {str(e)}")
    return ""

def scan_barcodes_from_pdf(pdf_path, page_range=None):
    """
    Extracts and scans all barcodes from a PDF file
    
    Args:
        pdf_path (str): Path to the PDF file
        page_range (tuple): Optional (start, end) page range to scan
        
    Returns:
        list: List of dictionaries containing barcode data
    """
    # Open the PDF file
    try:
        pdf_document = fitz.open(pdf_path)
        page_count = pdf_document.page_count
        
        # Set page range or use all pages
        start_page = 0
        end_page = page_count
        if page_range:
            start_page = max(0, page_range[0])
            end_page = min(page_count, page_range[1] + 1)
    except Exception as e:
        logging.error(f"Error opening PDF for barcode scanning: {e}")
        return []
    
    results = []
    
    # Process each page
    for page_num in range(start_page, end_page):
        # Convert PDF page to image
        try:
            page = pdf_document[page_num]
            # Higher zoom/dpi gives better resolution but slower processing
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Convert PIL image to OpenCV format (numpy array)
            img_cv = np.array(img)
            
            # Convert RGB to grayscale for better barcode detection
            gray = cv2.cvtColor(img_cv, cv2.COLOR_RGB2GRAY)
            
            # Improve image for barcode detection
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Detect barcodes
            barcodes = pyzbar.decode(gray)
            
            # Process detected barcodes
            for barcode in barcodes:
                barcode_data = barcode.data.decode("utf-8")
                barcode_type = barcode.type
                
                # Get barcode location
                (x, y, w, h) = barcode.rect
                
                results.append({
                    "page": page_num + 1,
                    "type": barcode_type,
                    "value": barcode_data,
                    "location": (x, y, w, h)
                })
        except Exception as e:
            logging.error(f"Error scanning barcodes on page {page_num}: {str(e)}")
    
    # Close the PDF
    pdf_document.close()
    
    return results

def extract_awb_from_pdf(pdf_path):
    """
    Extract AWB (tracking number) from a PDF shipping label using barcode scanning
    and text extraction techniques.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        str: Extracted AWB number or None if not found
    """
    # First try to extract AWB from barcodes
    try:
        # Try barcode scanning method first (most reliable)
        barcode_results = scan_barcodes_from_pdf(pdf_path)
        
        # AWB barcodes typically have specific formats
        awb_patterns = [
            r'\b1Z[0-9A-Z]{16}\b',           # UPS
            r'\b\d{12,14}\b',                # Most carriers use 12-14 digit tracking
            r'\b[A-Z]{2}\d{9}[A-Z]{2}\b',    # FedEx
            r'\b\d{20,22}\b',                # Some USPS/international
            r'\b[A-Z]{4}\d{10}\b'            # Amazon logistics format
        ]
        
        # Check barcode results against common AWB patterns
        if barcode_results:
            for result in barcode_results:
                barcode_value = result['value']
                # First check if any of our patterns match the barcode directly
                for pattern in awb_patterns:
                    match = re.search(pattern, barcode_value)
                    if match:
                        return match.group(0)
        
        # If barcode scanning fails, try text extraction
        # Open the PDF
        doc = fitz.open(pdf_path)
        
        # Focus on first 2 pages where shipping info is typically located
        for page_num in range(min(2, len(doc))):
            page = doc[page_num]
            text = page.get_text("text")
            text = clean_text(text)
            
            # Look for common AWB label patterns in text
            awb_text_patterns = [
                r'Tracking\s*(?:#|No|Number)?[:\s]*(\w+[\s-]?\w+)',
                r'AWB\s*(?:#|No|Number)?[:\s]*(\w+[\s-]?\w+)',
                r'Tracking\s*ID[:\s]*(\w+[\s-]?\w+)',
                r'Shipping\s*(?:Reference|ID)[:\s]*(\w+[\s-]?\w+)',
                r'Consignment\s*(?:#|No|Number)?[:\s]*(\w+[\s-]?\w+)',
                r'Waybill\s*(?:#|No|Number)?[:\s]*(\w+[\s-]?\w+)'
            ]
            
            for pattern in awb_text_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
            
            # Also check for standalone numbers that match AWB patterns
            for pattern in awb_patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(0)
        
        doc.close()
        return None
        
    except Exception as e:
        logging.error(f"Error extracting AWB: {str(e)}")
        return None

def extract_table_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    import camelot
    try:
        tables = camelot.read_pdf(pdf_path, pages=str(page_number))
        if tables.n > 0:
            df = tables[0].df  # Convert to DataFrame
            df.columns = df.iloc[0] # Set first row as header
            df = df[1:].reset_index(drop=True) # Remove first row
            desc_col = next((col for col in df.columns if 'description' in col.lower()), None)
            qty_col = next((col for col in df.columns if 'qty' in col.lower()), None)
            if desc_col and qty_col and "Qty" in df.columns:
                # Remove the rows above "TOTAL:"
                idx = df[df.apply(lambda row: row.astype(str).str.contains('TOTAL:', case=False, na=False).any(), axis=1)].index
                if not idx.empty and idx[0] > 0:
                    df = df.iloc[:idx[0]]  # Keep only the rows above "total"
                df_filtered = df[[desc_col, qty_col]]
                df_filtered = df_filtered.copy()
                sku_pattern = r"\(([^)]+)\)\s*HSN:"
                df_filtered.loc[:, "sku"] = (
                    df_filtered[desc_col]
                    .str.extract(sku_pattern)[0]  # Extract the first matched group
                    .astype(str)
                    .str.replace(r"\s+", " ", regex=True)  # Remove newlines and extra spaces
                    .str.strip()  # Trim spaces
                )
                df_filtered.drop(columns=desc_col, inplace=True, errors="ignore")
                return df_filtered.to_dict(orient='records')
        return None
    except Exception as e:
        logging.error(f"Error extracting table with camelot: {str(e)}")
        return None

# Data file reading functions
def txt_to_dataframe(file_path):
    """Reads a tab-delimited .txt file and converts it to a DataFrame."""
    try:
        df = pd.read_csv(file_path, delimiter='\t')
        return df
    except Exception as e:
        logging.error(f"Error reading txt file: {str(e)}")
        return pd.DataFrame()

def csv_to_dataframe(file_path):
    """Reads a CSV file and converts it to a DataFrame."""
    try:
        df = pd.read_csv(file_path, delimiter=',')
        return df
    except Exception as e:
        logging.error(f"Error reading CSV file: {str(e)}")
        return pd.DataFrame()

def excel_to_dataframe(file_path):
    """Reads an Excel file and converts it to a DataFrame."""
    try:
        if file_path.endswith('.xls'):
            df = pd.read_excel(file_path, engine='xlrd')
        else:  # for .xlsx
            df = pd.read_excel(file_path, engine='openpyxl')
        return df
    except Exception as e:
        logging.error(f"Error reading Excel file: {str(e)}")
        return pd.DataFrame()