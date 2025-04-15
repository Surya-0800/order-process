import os, csv
import re, camelot
import PyPDF2
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
import warnings
from datetime import datetime
import pandas as pd
import os
import cv2
import pyzbar.pyzbar as pyzbar
import numpy as np
from PIL import Image

##made
def extract_table_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    tables = camelot.read_pdf(pdf_path, pages=str(page_number))
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

def extract_order_details(text, second_page_flag= False):
    """Extract Order ID, SKU, and Quantity from text."""
    # orderid_match = re.search(r"Order\s*(ld|Id|Number):\s*[^0-9]*?(\d+)\s*[-~]?\s*(\d+)\s*[-~]?\s*(\d+)(?=$|\s|[^0-9])", text, re.IGNORECASE)
    if not second_page_flag:
      # orderid_match = re.search(r"Order\s*(1d|ld|Id):\s*[^0-9]*?(\d+)[\s.\-~]*(\d+)[\s.\-~]*(\d+)", text, re.IGNORECASE)
      orderid_match = re.search(r"Order\s*(1d|ld|Id|Number):\s*[^0-9]*?(\d+)[\s.\-~]*(\d+)[\s.\-~]*(\d+)", text, re.IGNORECASE)
      first_page_match = re.search(r"Ship to:|Ship From:", text, re.IGNORECASE)
      
      orderid = f"{orderid_match.group(2)}-{orderid_match.group(3)}-{orderid_match.group(4)}" if orderid_match else None
      number_or_id = orderid_match.group(1) if orderid_match else None
    else:
      orderid_match = re.search(r"Order\s*(1d|ld|Id|Number):\s*[^0-9]*?(\d+)[\s.\-~]*(\d+)[\s.\-~]*(\d+)", text, re.IGNORECASE)
      number_or_id = None
      first_page_match = re.search(r"Ship to:|Ship From:", text, re.IGNORECASE) 
    return orderid, number_or_id, bool(first_page_match)
  
def clean_text(text):
    """Clean text by removing extra spaces, newlines, etc."""
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)  # Remove non-ASCII characters
    text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace
    text = text.replace("—", "-")  # Replace OCR misrecognized dashes
    return text

def extract_text_from_page(page,pdf_path, ocr=False):
    """Extract text using PyMuPDF or OCR if necessary."""
    text = page.get_text("text")
    if not text.strip() and ocr:
        # Convert page to image and apply OCR
        pix = page.get_pixmap()
        image = convert_from_path(pdf_path, first_page=page.number+1, last_page=page.number+1,poppler_path=r"C:\poppler\poppler-24.08.0\Library\bin")[0]
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(image, config = custom_config)
    return clean_text(text)

def split_pdf_by_orderid(pdf_path, output_folder, final_output_dict):
    """Splits a PDF into separate PDFs based on OrderID and extracts AWB."""
    # Filter warnings about CropBox
    warnings.filterwarnings("ignore", message="CropBox missing from /Page")
    
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    order_pages = {}
    doc = fitz.open(pdf_path)
    skip_page_for_now = []
    prev_order_id= ""
    order_details = {}
    
    for i, page in enumerate(doc):
        text = extract_text_from_page(page, pdf_path)
        # Remove the debugging breakpoint
        # import pdb;pdb.set_trace()
        
        #if first page text is empty which is always empty go find order id on the next page or skip that page for now with detals of the page in 
        if text:
            orderid, number_or_id, first_page_match = extract_order_details(text)
            if orderid:
                orderid = orderid.replace("-","")
                orderid = f"{orderid[:3]}-{orderid[3:10]}-{orderid[10:]}"
                
                # Extract items from final_output_dict for this order
                matching_items = [d for d in final_output_dict if d["order-id"] == orderid]
                
                # Check if we have AWB in the data
                has_awb = matching_items and "tracking-id" in matching_items[0] and matching_items[0]["tracking-id"]
                
                # Create order details
                if matching_items:
                    order_details = {orderid: [{"sku": d["sku"], "Qty": d["quantity-purchased"], 
                                              "AWB": d.get("tracking-id", "")} for d in matching_items]}
                else:
                    order_details = {orderid: []}
                
                # If no AWB in the data, try to extract it from the PDF
                if not has_awb and (not order_details[orderid] or not order_details[orderid][0].get("AWB")):
                    # Create a temporary PDF with just this page for AWB extraction
                    temp_pdf_path = os.path.join(output_folder, f"_temp_{orderid}.pdf")
                    temp_doc = fitz.open()
                    temp_doc.insert_pdf(doc, from_page=i, to_page=i)
                    temp_doc.save(temp_pdf_path)
                    temp_doc.close()
                    
                    # Extract AWB from the temporary PDF
                    awb = extract_awb_from_pdf(temp_pdf_path)
                    
                    # Clean up the temporary file
                    try:
                        os.remove(temp_pdf_path)
                    except:
                        pass
                    
                    # Update order details with extracted AWB
                    if awb:
                        if order_details[orderid]:
                            for item in order_details[orderid]:
                                item["AWB"] = awb
                        else:
                            # If no items were found, create a placeholder with just the AWB
                            order_details[orderid] = [{"sku": "Unknown", "Qty": "1", "AWB": awb}]
                
                # If still no order details, try extracting table data
                if not order_details[orderid]:
                    print(f"No order details found for order {orderid}")
                    extracted_items = extract_table_with_camelot(pdf_path, i+1)
                    if extracted_items:
                        # Add AWB to extracted items if we found one
                        if 'awb' in locals() and awb:
                            for item in extracted_items:
                                item["AWB"] = awb
                        order_details[orderid] = extracted_items
                
                # Initialize order_pages entry if needed
                if orderid not in order_pages:
                    if skip_page_for_now:
                        order_pages[orderid] = skip_page_for_now
                        if order_details[orderid]:
                            order_pages[orderid].append(order_details[orderid])
                            order_details = {}
                    else:
                        order_pages[orderid] = []
                
                order_pages[orderid].append(i)
                skip_page_for_now = []
                prev_order_id = orderid
            elif number_or_id and number_or_id != "Number":
                skip_page_for_now = [i]
            elif first_page_match:
                skip_page_for_now = [i]
            else:
                if prev_order_id and prev_order_id in order_pages:
                    order_pages[prev_order_id].append(i)
                prev_order_id = ""
        else:
            skip_page_for_now = [i]
        
        if order_details and not skip_page_for_now:
            if orderid:
                order_pages[orderid].append(order_details[orderid])
                order_details = {}
            elif prev_order_id and prev_order_id in order_pages:
                order_pages[prev_order_id].append(order_details[prev_order_id])
                order_details = {}

    # Remainder of the function (processing PDFs) remains unchanged...
    # Process each order and create resized PDFs using a different approach
    for orderid, pages in order_pages.items():
        # Filter only integer page numbers
        page_nums = [p for p in pages if isinstance(p, int)]
        
        if not page_nums:
            continue
            
        # We'll use a completely different approach that doesn't rely on PyMuPDF's show_pdf_page
        try:
            # Step 1: Generate a 4x6 inch image of the first page
            first_page_idx = page_nums[0]
            
            # Create a temporary directory if it doesn't exist
            temp_dir = os.path.join(output_folder, "_temp")
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            # Convert first page to image with resolution suitable for 4x6 at 300 DPI
            # (4 inches * 300 DPI = 1200 pixels wide, 6 inches * 300 DPI = 1800 pixels tall)
            page = doc[first_page_idx]
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))  # 300 DPI
            img_path = os.path.join(temp_dir, f"_temp_first_page_{orderid}.png")
            pix.save(img_path)
            
            # Create a new PDF with a 4x6 inch page
            new_doc = fitz.open()
            new_page = new_doc.new_page(width=4*72, height=6*72)  # 4x6 inches in points
            
            # Insert the image, scaled to fit
            rect = new_page.rect
            new_page.insert_image(rect, filename=img_path)
            
            # Save the first page to a temporary PDF
            first_page_pdf = os.path.join(temp_dir, f"_temp_first_page_{orderid}.pdf")
            new_doc.save(first_page_pdf)
            new_doc.close()
            
            # Now use PyPDF2 to combine this with the remaining pages
            with open(pdf_path, "rb") as infile, open(first_page_pdf, "rb") as temp_file:
                reader = PyPDF2.PdfReader(infile)
                first_reader = PyPDF2.PdfReader(temp_file)
                writer = PyPDF2.PdfWriter()
                
                # Add the 4x6 first page
                writer.add_page(first_reader.pages[0])
                
                # Add remaining pages
                for page_idx in page_nums[1:]:
                    writer.add_page(reader.pages[page_idx])
                
                # Save the final PDF
                output_pdf_path = os.path.join(output_folder, f"Order_{orderid}.pdf")
                with open(output_pdf_path, "wb") as output_pdf:
                    writer.write(output_pdf)
                
                # Add output path to order pages
                order_pages[orderid].append({"output_pdf_location": output_pdf_path})
            
            # Clean up temporary files
            try:
                os.remove(img_path)
                os.remove(first_page_pdf)
            except:
                pass
                
        except Exception as e:
            print(f"Error resizing first page for order {orderid}: {str(e)}")
            print("Falling back to original page sizes")
            
            # Fallback to original code if resizing fails
            with open(pdf_path, "rb") as infile:
                reader = PyPDF2.PdfReader(infile)
                writer = PyPDF2.PdfWriter()
                
                for page_num in pages:
                    if isinstance(page_num, int):
                        writer.add_page(reader.pages[page_num])
                
                output_pdf_path = os.path.join(output_folder, f"Order_{orderid}.pdf")
                order_pages[orderid].append({"output_pdf_location": output_pdf_path})
                
                with open(output_pdf_path, "wb") as output_pdf:
                    writer.write(output_pdf)
    
    return order_pages

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

def txt_to_dataframe(file_path):
    """
    Reads a tab-delimited .txt file and converts it to a Pandas DataFrame.
    :param file_path: Path to the .txt file
    :return: Pandas DataFrame
    """
    df = pd.read_csv(file_path, delimiter='\t')
    return df

def grab_required_fields(data):
    required_columns = ["order-id", "sku", "quantity-purchased","tracking-id"]  # Replace with actual column names
    filtered_data = [{col: row[col] for col in required_columns if col in row} for row in data]
    return filtered_data

