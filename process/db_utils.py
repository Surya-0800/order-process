# db_utils.py
import os
from django.db import transaction
from ordercycle.models import OrderPDF
import json

def save_pdf_to_database(order_id, pdf_path, order_details=None, source_type="default"):
    """
    Save a PDF file to the PostgreSQL database
    
    Args:
        order_id (str): The order ID to use as primary key
        pdf_path (str): Path to the PDF file
        order_details (list, optional): List of order items with SKU, quantity, etc.
        source_type (str): Identifier for which script processed this file
    
    Returns:
        OrderPDF: The created or updated OrderPDF object
    """
    try:
        # Read the PDF file content
        with open(pdf_path, 'rb') as file:
            pdf_content = file.read()
        
        # Extract filename from path
        filename = os.path.basename(pdf_path)
        
        # Prepare metadata - store order details if provided
        metadata = {}
        if order_details:
            # Convert to simple types for JSON serialization
            metadata['items'] = order_details
            
        # Use atomic transaction to ensure database consistency
        with transaction.atomic():
            # Get or create the OrderPDF object
            order_pdf, created = OrderPDF.objects.update_or_create(
                order_id=order_id,
                defaults={
                    'pdf_content': pdf_content,
                    'filename': filename,
                    'source_type': source_type,
                    'metadata': metadata
                }
            )
            
            return order_pdf, created
    except Exception as e:
        # Log the error
        print(f"Error saving PDF to database: {str(e)}")
        raise