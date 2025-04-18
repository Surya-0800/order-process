import os
import io
from PIL import Image
import numpy as np
import cv2
import pyzbar.pyzbar as pyzbar
import fitz  # PyMuPDF

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
        print(f"Processing page {page_num + 1} of {len(pdf_document)}")
        
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
            
            print(f"Barcode found on page {page_num + 1}: {barcode_data} ({barcode_type})")
    
    # Close the PDF
    pdf_document.close()
    
    return results


def save_barcode_images(pdf_path, output_dir="barcode_images"):
    """
    Extracts images of detected barcodes from a PDF file and saves them
    
    Args:
        pdf_path (str): Path to the PDF file
        output_dir (str): Directory to save barcode images
        
    Returns:
        list: List of paths to the saved barcode images
    """
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    pdf_document = fitz.open(pdf_path)
    saved_images = []
    
    for page_num, page in enumerate(pdf_document):
        pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_cv = np.array(img)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_RGB2GRAY)
        
        # Detect barcodes
        barcodes = pyzbar.decode(gray)
        
        for i, barcode in enumerate(barcodes):
            # Extract barcode location
            (x, y, w, h) = barcode.rect
            
            # Add some padding to the barcode area
            padding = 10
            x_start = max(0, x - padding)
            y_start = max(0, y - padding)
            x_end = min(img_cv.shape[1], x + w + padding)
            y_end = min(img_cv.shape[0], y + h + padding)
            
            # Extract barcode image
            barcode_img = img_cv[y_start:y_end, x_start:x_end]
            
            # Save barcode image
            barcode_data = barcode.data.decode("utf-8")
            safe_data = "".join([c if c.isalnum() else "_" for c in barcode_data])[:30]  # sanitize filename
            image_path = os.path.join(output_dir, f"page{page_num+1}_barcode{i+1}_{safe_data}.png")
            cv2.imwrite(image_path, cv2.cvtColor(barcode_img, cv2.COLOR_RGB2BGR))
            saved_images.append(image_path)
    
    pdf_document.close()
    return saved_images


def main():
    # Get PDF path from user
    pdf_path = r"C:\Users\teja0\Downloads\Order Process Cycle-20250403T030855Z-001\Order Process Cycle\orderCycleProject\media\amazonPdfs\Order_407-6219961-6502708.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"Error: File does not exist at {pdf_path}")
        return
    
    # Scan barcodes
    print(f"Scanning barcodes in {pdf_path}...")
    barcode_results = scan_barcodes_from_pdf(pdf_path)
    
    # Print results
    if barcode_results:
        print("\nBarcode Scan Results:")
        print("-" * 50)
        for result in barcode_results:
            print(f"Page {result['page']}: {result['value']} ({result['type']})")
        
        # Ask if user wants to save barcode images
        save_images = input("\nDo you want to save images of the barcodes? (y/n): ").lower() == "y"
        if save_images:
            output_dir = input("Enter output directory (default: barcode_images): ") or "barcode_images"
            saved_paths = save_barcode_images(pdf_path, output_dir)
            print(f"\nSaved {len(saved_paths)} barcode images to {output_dir}")
    else:
        print("No barcodes were detected in the PDF.")


if __name__ == "__main__":
    main()


