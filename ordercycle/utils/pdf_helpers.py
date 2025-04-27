"""
Utility functions for PDF processing.
"""
import fitz  # PyMuPDF

def extract_text_from_first_page(pdf_path):
    """
    Extract text from the first page of a PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        str: Extracted text from the first page
    """
    try:
        # Open the PDF
        pdf_document = fitz.open(pdf_path)
        
        # Get the first page
        first_page = pdf_document[0]
        
        # Extract text from the first page
        text = first_page.get_text()
        
        # Close the PDF
        pdf_document.close()
        
        return text
    except Exception as e:
        # Handle any errors
        print(f"Error extracting text from PDF: {e}")
        return ""