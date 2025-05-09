import fitz  # PyMuPDF
import os, camelot
import pandas as pd
import re, csv
from itertools import zip_longest
from datetime import datetime
import io
from PIL import Image, ImageChops
import numpy as np
import cv2
from pyzbar import pyzbar

def extract_awb_from_text(text):
    """
    Extract AWB number from shipping label text using more dynamic regex patterns.
    Handles various AWB formats including different prefixes and number patterns.
    
    Args:
        text (str): Text extracted from the shipping label/invoice
        
    Returns:
        str: Extracted AWB number or None if not found
    """
    # Priority 1: Look for explicit "AWB No." or related labels followed by AWB
    awb_label_patterns = [
        # AWB No. FMPP2877530189
        r'AWB\s*(?:No\.?|Number|#)?\s*[:\.]?\s*([A-Z0-9]{8,18})',
        # Tracking ID: FMPP2877530189
        r'Tracking\s*(?:ID|Number|No\.?|#)?\s*[:\.]?\s*([A-Z0-9]{8,18})',
        # Waybill No.: FMPP2877530189
        r'Waybill\s*(?:No\.?|Number|#)?\s*[:\.]?\s*([A-Z0-9]{8,18})',
        # Consignment Number: FMPP2877530189
        r'Consignment\s*(?:No\.?|Number|#)?\s*[:\.]?\s*([A-Z0-9]{8,18})',
        # Shipping ID: FMPP2877530189
        r'Shipping\s*(?:ID|Number|No\.?)?\s*[:\.]?\s*([A-Z0-9]{8,18})'
    ]
    
    # Try patterns with explicit labels first
    for pattern in awb_label_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result = match.group(1).strip()
            # Skip if it looks like an order ID (usually has "OD" prefix)
            if not re.match(r'^OD\d+$', result):
                return result
    
    # Priority 2: Look for common courier format patterns without labels
    # These are more varied and include multiple carrier formats
    courier_patterns = [
        # E-Kart specific formats (FM prefix with 2 letters and digits)
        r'\b(FM[A-Z]{2}\d{8,12})\b',  
        # E-Kart alternative formats
        r'\b(FM[A-Z]{0,1}\d{10,14})\b',  
        # FMPP, FMBC, FMCC followed by digits
        r'\b(FM[A-Z]{2}\d{10,14})\b',
        # Other common courier alpha-numeric formats (2-4 letters followed by 8-12 digits)
        r'\b([A-Z]{2,4}\d{8,12})\b',
        # Pure numeric tracking numbers (12-14 digits)
        r'\b(\d{7,})\b',
        # FedEx format (2 letters, 9-10 digits, 2 letters)
        r'\b([A-Z]{2}\d{9,10}[A-Z]{2})\b',
        # Alternative format (digits followed by letters)
        r'\b(\d{10,12}[A-Z]{2,4})\b'
    ]
    
    # Find all matches for courier patterns
    all_matches = []
    for pattern in courier_patterns:
        matches = re.findall(pattern, text)
        all_matches.extend(matches)
    
    # Filter out order IDs and other non-AWB matches
    filtered_matches = [match for match in all_matches if not re.match(r'^OD\d+$', match)]
    
    if filtered_matches:
        # Sort matches by length (longer matches are more likely to be AWBs)
        sorted_matches = sorted(filtered_matches, key=len, reverse=True)
        
        # Additional filtering to improve quality
        # Prefer matches with FM prefix if available
        fm_matches = [m for m in sorted_matches if m.startswith('FM')]
        if fm_matches:
            return fm_matches[0]
        
        # Otherwise return the longest match
        return sorted_matches[0]
    
    # Priority 3: Check if AWB appears near the order ID (common in invoices)
    order_id_pattern = r'Order\s*(?:Id|ID|No\.?)?\s*:?\s*(OD\d+)'
    order_match = re.search(order_id_pattern, text, re.IGNORECASE)
    
    if order_match:
        # Find text surrounding the order ID (200 chars before and 400 chars after)
        order_id_pos = text.find(order_match.group(0))
        start_pos = max(0, order_id_pos - 200)
        end_pos = min(len(text), order_id_pos + 400)
        surrounding_text = text[start_pos:end_pos]
        
        # Apply all patterns to this region
        for pattern in courier_patterns:
            matches = re.findall(pattern, surrounding_text)
            # Filter out the actual order ID
            filtered = [m for m in matches if m != order_match.group(1)]
            if filtered:
                # Sort by length and return the longest
                sorted_matches = sorted(filtered, key=len, reverse=True)
                return sorted_matches[0]
    
    # Priority 4: Last resort - look for numeric sequences that might be AWBs
    # This is less reliable but can catch numeric-only AWBs
    numeric_patterns = [
        r'\b(\d{10,14})\b'  # 10-14 digit numbers (common AWB length)
    ]
    
    for pattern in numeric_patterns:
        matches = re.findall(pattern, text)
        if matches:
            # Filter out dates, phone numbers, and other common numeric patterns
            filtered = []
            for match in matches:
                # Skip phone numbers (usually 10 digits)
                if len(match) == 10 and match.startswith(('9', '8', '7', '6')):
                    continue
                # Skip dates (DDMMYYYY, YYYYMMDD formats)
                if re.match(r'^\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{2}$', match):
                    continue
                filtered.append(match)
            
            if filtered:
                # Return the longest numeric sequence
                sorted_matches = sorted(filtered, key=len, reverse=True)
                return sorted_matches[0]
    
    # No AWB found
    return None

def extract_text_with_fitz(input_pdf, page_num):
    doc = fitz.open(input_pdf)
    page = doc[page_num]
    text = page.get_text("text")
    awb = extract_awb_from_text(text)
    order_id_match = re.search(r"E-Kart Logistics\s*\n*(OD\d+)", text)
    match = re.search(r"SKU(.*?)Invoice", text, re.DOTALL)
    if match:
        lines = match.group(1).split("\n")
        filtered_lines = lines[:4]
        keys = filtered_lines[:2]
        values = filtered_lines[2:]
        value_chunks = [values[i:i+2] for i in range(0, len(values), 2)]
        data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
        data_dict["Order No."] = [order_id_match.group(1)]
        if awb:
            data_dict["AWB"] = [awb]
        return data_dict
    else:
        if order_id_match and awb:
            return {"Order No.": [order_id_match.group(1)], "AWB": [awb]}
        return {}

def extract_text_with_camelot(pdf_path, page_number):
    tables = camelot.read_pdf(pdf_path, pages=str(page_number))
    if tables.n > 0:
        digit_match = re.compile(r"\d_\d", re.IGNORECASE)
        df = tables[0].df
        filtered_df = df[df.apply(lambda row: row.astype(str).str.contains("Product Details", case=False, na=False).any(), axis=1)]
        if filtered_df.empty:
            return {}
        text = filtered_df.iloc[(0,0)]
        lines = text.split("\n")
        remove_values = {"Product Details", "Original For Recipient", "TAX INVOICE"}
        filtered_lines = [line for line in lines if line not in remove_values]
        if filtered_lines[4] != "Order No.":
            filtered_lines.insert(4, "Order No.")
        order_matching_pos = [i for i, item in enumerate(filtered_lines) if digit_match.search(item)]
        if order_matching_pos:
            match_index = order_matching_pos[0]
            if match_index != 9:
                value = filtered_lines.pop(match_index)
                if len(filtered_lines) < 10:
                    filtered_lines.extend([""] * (10 - len(filtered_lines)))
                if "free size" in filtered_lines[5].lower():
                    filtered_lines[5] = filtered_lines[5].split("Free Size")[0].strip()
                    filtered_lines.insert(6, "Free Size")
                    filtered_lines.pop()
                    filtered_lines[9] = value
        keys = filtered_lines[:5]
        values = filtered_lines[5:]
        value_chunks = [values[i:i+5] for i in range(0, len(values), 5)]
        data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
        return data_dict
    else:
        return {}

def split_pdf_custom(input_pdf, output_folder, final_output_dict, top_ratio=0.46):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    temp_dir = os.path.join(output_folder, "_temp")
    os.makedirs(temp_dir, exist_ok=True)
    doc = fitz.open(input_pdf)
    order_pages = {}

    for page_num, page in enumerate(doc):
        if result_dict := extract_text_with_fitz(input_pdf, page_num):
            if not result_dict.get("Order No."):
                result_dict = extract_text_with_camelot(input_pdf, page_num+1)
        else:
            result_dict = extract_text_with_camelot(input_pdf, page_num+1)

        if result_dict.get("Order No."):
            new_doc = fitz.open()
            page = doc[page_num]
            rect = page.rect
            top_height = rect.height * top_ratio
            bottom_height = rect.height + 1 - top_height
            top_rect = fitz.Rect(0, 0, rect.width, top_height - 3)
            top_page = new_doc.new_page(width=rect.width, height=top_height)
            top_page.show_pdf_page(top_page.rect, doc, page_num, clip=top_rect)
            bottom_rect = fitz.Rect(0, top_height, rect.width, rect.height)
            bottom_page = new_doc.new_page(width=rect.width, height=bottom_height)
            bottom_page.show_pdf_page(bottom_page.rect, doc, page_num, clip=bottom_rect)
            df = pd.DataFrame(result_dict)
            orderid_name = "_".join(set([i.split("_")[0] for i in result_dict.get("Order No.", [])]))
            split_pdf_path = os.path.join(temp_dir, f"split_{orderid_name}.pdf")
            new_doc.save(split_pdf_path)
            new_doc.close()

            # Create the final output PDF directly from the split PDF
            final_doc = fitz.open()
            split_doc = fitz.open(split_pdf_path)
            
            # Simply include all pages from the split document without 4x6 conversion
            for i in range(len(split_doc)):
                final_doc.insert_pdf(split_doc, from_page=i, to_page=i)
                
            output_pdf_path = os.path.join(output_folder, f"Order_{orderid_name}.pdf")
            final_doc.save(output_pdf_path)
            final_doc.close()
            split_doc.close()

            for i in df.to_dict(orient="records"):
                orderid = i.get("Order No.")
                if not orderid:
                    continue
                
                # Get AWB from the result_dict if it exists
                extracted_awb = i.get("AWB")
                
                sku_qty_items = [{"sku": d["SKU"], "Qty": d["Quantity"], "AWB": d["Tracking ID"]} for d in final_output_dict if d["Order Id"] == orderid]
                
                # Update items with missing AWB
                for item in sku_qty_items:
                    if (not item.get("AWB") or item.get("AWB") == "" or item.get("AWB") is None) and extracted_awb:
                        item["AWB"] = extracted_awb
                        # Also update the main final_output_dict
                        for d in final_output_dict:
                            if d["Order Id"] == orderid and d["SKU"] == item["sku"]:
                                d["Tracking ID"] = extracted_awb
                
                if not sku_qty_items:
                    sku = i.get(" ID | Description", "").split("|")[0].split(" ")[1] if i.get(" ID | Description") else ""
                    
                    new_item = {"sku": sku, "Qty": i.get("QTY")}
                    # Add AWB if available
                    if extracted_awb:
                        new_item["AWB"] = extracted_awb
                    
                    sku_qty_items = [new_item]
                
                if str(orderid) not in order_pages:
                    order_pages[str(orderid)] = [sku_qty_items]
                else:
                    if isinstance(order_pages[str(orderid)][0], list):
                        for item in sku_qty_items:
                            if item not in order_pages[str(orderid)][0]:
                                order_pages[str(orderid)][0].append(item)
                    else:
                        order_pages[str(orderid)] = [sku_qty_items]
            if str(orderid) in order_pages:
                if not any(isinstance(i, dict) and "output_pdf_location" in i for i in order_pages[str(orderid)]):
                    order_pages[str(orderid)].append({"output_pdf_location": output_pdf_path})
        else:
            if 'output_pdf_path' in locals() and os.path.exists(output_pdf_path):
                new_doc = fitz.open(output_pdf_path)
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                new_doc.insert_page(-1)
                output_pdf_path_temp = os.path.join(output_folder, f"Order_{orderid_name}_temp.pdf")
                new_doc.save(output_pdf_path_temp)
                new_doc.close()
                os.remove(output_pdf_path)
                os.rename(output_pdf_path_temp, output_pdf_path)

    if os.path.exists(temp_dir):
        for temp_file in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, temp_file))
            except:
                pass
        try:
            os.rmdir(temp_dir)
        except:
            pass

    return order_pages

def csv_to_dataframe(file_path):
    df = pd.read_csv(file_path, delimiter=',')
    return df

def grab_required_fields(data):
    required_columns = ["Order Id", "SKU", "Quantity", "Tracking ID"]
    filtered_data = [{col: row[col] for col in required_columns if col in row} for row in data]
    return filtered_data

def clean_text(text):
    """
    Clean and normalize extracted text for better pattern matching
    """
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Normalize common separators
    text = re.sub(r'[_\.\-]', ' ', text)
    return text.strip()

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
