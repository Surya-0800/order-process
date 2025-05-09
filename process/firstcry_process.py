import os, csv
import re, camelot
import PyPDF2
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
import warnings
from datetime import datetime
import pandas as pd
import cv2
import pyzbar.pyzbar as pyzbar
import numpy as np
from PIL import Image

##made
def extract_table_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    import pdb
    tables = camelot.read_pdf(pdf_path, pages=str(page_number))
    pdb.set_trace()
    if tables.n > 0:
        df = tables[0].df  # Convert to DataFrame
        df.columns = df.iloc[0] # Set first row as header
        df = df[1:].reset_index(drop=True) # Remove first row
        desc_col = next((col for col in df.columns if 'description' in col.lower()), None)
        qty_col = next((col for col in df.columns if 'qty' in col.lower()), None)
        if desc_col and qty_col and "Qty" in df.columns:
          #remove the rows above "TOTAL:"
          idx = df[df.apply(lambda row: row.astype(str).str.contains('TOTAL:', case=False, na=False).any(), axis=1)].index
          if not idx.empty and idx[0] > 0:
              df = df.iloc[:idx[0]]  # Keep only the rows above "total"
          df_filtered = df[[desc_col, qty_col]]
          df_filtered = df_filtered.copy()
          sku_pattern = r"\(([^)]+)\)\s*HSN:"
          # df_filtered["sku"] = df_filtered[desc_col].str.extract(sku_pattern)
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

def extract_order_details(text):
    """Extract Order ID, SKU, and Quantity from text."""
    # need to change the regex pattern to match the order id
    orderid_match = re.search(r"Order No\s*:\s*([\w\d]+)", text, re.IGNORECASE)
    scanner_page_match = re.search(r"Ship to:|Ship From:", text, re.IGNORECASE)
    
    orderid = orderid_match.group(1) if orderid_match else None
    
    return orderid, bool(scanner_page_match)
  
def clean_text(text):
    """Clean text by removing extra spaces, newlines, etc."""
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)  # Remove non-ASCII characters
    text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace
    text = text.replace("—", "-")  # Replace OCR misrecognized dashes
    return text

def extract_text_from_page(page,pdf_path):
    """Extract text using PyMuPDF or OCR if necessary."""
    text = page.get_text("text")
    if not text.strip():
        # Convert page to image and apply OCR
        pix = page.get_pixmap()
        image = convert_from_path(pdf_path, first_page=page.number+1, last_page=page.number+1)[0]
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(image, config = custom_config)
    return clean_text(text)

def split_pdf_by_orderid(pdf_path, output_folder, final_output_dict):
    """Splits a PDF into separate PDFs based on OrderID."""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    order_pages = {}
    doc = fitz.open(pdf_path)
    skip_page_for_now = []
    prev_order_id= ""
    order_details = {}
    
    for i, page in enumerate(doc):
        text = extract_text_from_page(page,pdf_path)
        import pdb
        pdb.set_trace()
        if text:
            orderid, scanner_page_match = extract_order_details(text)
            if orderid != prev_order_id:
              if orderid:
                prev_order_id = orderid
            
            if orderid:
                order_details = {orderid: [{"sku": d["Vendor Style Code"], "Qty": d["Total Qty"], "Items": d["Total Items"],"AWB":d["AWB No"]} for d in final_output_dict if d["Order ID"] == orderid]}
                if not order_details[orderid]:
                  order_details[orderid] = extract_table_with_camelot(pdf_path, i+1)
                if orderid not in order_pages and not skip_page_for_now:
                    order_pages[orderid] = []
                elif orderid not in order_pages and skip_page_for_now:
                    order_pages[orderid] = skip_page_for_now
                order_pages[orderid].append(i)
                skip_page_for_now = []
            elif scanner_page_match:
                skip_page_for_now = [i]
            else:
                order_pages[prev_order_id].append(i)
        if order_details and not skip_page_for_now:
            if orderid:
                import pdb
                pdb.set_trace()
                # Check if AWB is missing for this order
                for item in order_details[orderid]:
                    if not item.get("AWB") or pd.isna(item.get("AWB")) or item.get("AWB") == "":
                        # Create a temporary single-page PDF to extract AWB
                        temp_pdf_path = os.path.join(output_folder, f"temp_{orderid}_{i}.pdf")
                        temp_writer = PyPDF2.PdfWriter()
                        with open(pdf_path, "rb") as temp_infile:
                            temp_reader = PyPDF2.PdfReader(temp_infile)
                            temp_writer.add_page(temp_reader.pages[i])
                            with open(temp_pdf_path, "wb") as temp_pdf:
                                temp_writer.write(temp_pdf)
                        
                        # Try to extract AWB from this page
                        extracted_awb = extract_awb_from_pdf(temp_pdf_path)
                        
                        # Clean up temp file
                        try:
                            os.remove(temp_pdf_path)
                        except:
                            pass
                            
                        # Update AWB if found
                        if extracted_awb:
                            item["AWB"] = extracted_awb
                
                order_pages[orderid].append(order_details[orderid])
                order_details = {}
            else:
                # Check if AWB is missing for this order
                for item in order_details[prev_order_id]:
                    if not item.get("AWB") or pd.isna(item.get("AWB")) or item.get("AWB") == "":
                        # Create a temporary single-page PDF to extract AWB
                        temp_pdf_path = os.path.join(output_folder, f"temp_{prev_order_id}_{i}.pdf")
                        temp_writer = PyPDF2.PdfWriter()
                        with open(pdf_path, "rb") as temp_infile:
                            temp_reader = PyPDF2.PdfReader(temp_infile)
                            temp_writer.add_page(temp_reader.pages[i])
                            with open(temp_pdf_path, "wb") as temp_pdf:
                                temp_writer.write(temp_pdf)
                        
                        # Try to extract AWB from this page
                        extracted_awb = extract_awb_from_pdf(temp_pdf_path)
                        
                        # Clean up temp file
                        try:
                            os.remove(temp_pdf_path)
                        except:
                            pass
                            
                        # Update AWB if found
                        if extracted_awb:
                            item["AWB"] = extracted_awb
                
                order_pages[prev_order_id].append(order_details[prev_order_id])
                order_details = {}

    
    # Create PDFs for each OrderID
    with open(pdf_path, "rb") as infile:
        reader = PyPDF2.PdfReader(infile)
        
        for orderid, pages in order_pages.items():
            writer = PyPDF2.PdfWriter()
            for page_num in pages:
                if isinstance(page_num, int):
                  writer.add_page(reader.pages[page_num])
            
            output_pdf_path = os.path.join(output_folder, f"Order_{orderid}.pdf")
            order_pages[orderid].append({"output_pdf_location" : output_pdf_path})
            
            with open(output_pdf_path, "wb") as output_pdf:
                writer.write(output_pdf)
                
            # After creating the full order PDF, try one more time to extract AWB if not found earlier
            # Find the order details in the pages list
            order_items = None
            for item in pages:
                if not isinstance(item, int) and isinstance(item, list):
                    order_items = item
                    break
            
            if order_items:
                # Check if any item is missing AWB
                missing_awb = False
                for item in order_items:
                    if not item.get("AWB") or pd.isna(item.get("AWB")) or item.get("AWB") == "":
                        missing_awb = True
                        break
                
                if missing_awb:
                    # Try to extract AWB from the full order PDF
                    extracted_awb = extract_awb_from_pdf(output_pdf_path)
                    if extracted_awb:
                        # Update AWB for all items in this order
                        for item in order_items:
                            if not item.get("AWB") or pd.isna(item.get("AWB")) or item.get("AWB") == "":
                                item["AWB"] = extracted_awb
    
    return order_pages

def excel_to_dataframe(file_path):
    if file_path.endswith('.xls'):
        df = pd.read_excel(file_path, engine='xlrd')
    else:  # for .xlsx
        df = pd.read_excel(file_path, engine='openpyxl')
    return df

def grab_required_fields(data):
    required_columns = ["Order ID", "Vendor Style Code", "Total Items", "Total Qty","AWB No"]  # Replace with actual column names
    filtered_data = [{col: row[col] for col in required_columns if col in row} for row in data]
    return filtered_data

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
        # Open the PDF
        doc = fitz.open(pdf_path)
        
        # Try barcode scanning method first (most reliable)
        barcode_results = scan_barcodes_from_pdf(pdf_path)
        
        # AWB barcodes typically have specific formats:
        # - Usually starts with 1Z for UPS
        # - Often 12-14 digits for most carriers
        # - Sometimes prefixed with carrier code
        
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
        # Focus on first 1-2 pages where shipping info is typically located
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
        print(f"Error extracting AWB: {str(e)}")
        return None

def scan_barcodes_from_pdf(pdf_path):
    """
    Extracts and scans all barcodes from a PDF file
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        list: List of dictionaries containing barcode data
    """
    # Open the PDF file
    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error opening PDF: {e}")
        return []
    
    results = []
    
    # Process each page
    for page_num, page in enumerate(pdf_document):
        # Convert PDF page to image
        # Higher zoom/dpi gives better resolution but slower processing
        pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
        
        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Convert PIL image to OpenCV format (numpy array)
        img_cv = np.array(img)
        
        # Convert RGB to grayscale for better barcode detection
        gray = cv2.cvtColor(img_cv, cv2.COLOR_RGB2GRAY)
        
        # Optional: Improve image for barcode detection
        # This can help with low quality images or hard to detect barcodes
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
    
    # Close the PDF
    pdf_document.close()
    
    return results
