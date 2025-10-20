"""
Database utilities for handling PDF storage.
Optimized to use file system instead of binary database storage.
"""
import os
from pathlib import Path
from django.db import transaction
from django.conf import settings
from django.core.files import File
from ordercycle.models import OrderPDF


def save_pdf_to_database(order_id, pdf_path, order_details=None, source_type="default"):
    """
    Save a PDF file to the file system via OrderPDF model.
    
    This function stores PDFs on the file system for optimal performance,
    not as binary data in the database.
    
    Args:
        order_id (str): The order ID to use as primary key
        pdf_path (str): Path to the PDF file
        order_details (list, optional): List of order items with SKU, quantity, etc.
        source_type (str): Identifier for which script processed this file
    
    Returns:
        tuple: (OrderPDF object, created boolean)
    
    Raises:
        FileNotFoundError: If pdf_path doesn't exist
        Exception: For other errors during save
    """
    try:
        # Verify file exists
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found at: {pdf_path}")
        
        # Extract filename from path
        filename = os.path.basename(pdf_path)
        
        # Prepare metadata - store order details if provided
        metadata = {}
        if order_details:
            metadata['items'] = order_details
        
        # Use atomic transaction to ensure database consistency
        with transaction.atomic():
            # Check if OrderPDF already exists
            existing_pdf = OrderPDF.objects.filter(order_id=order_id).first()
            
            if existing_pdf:
                # Update existing record
                print(f"Updating existing PDF for order {order_id}")
                
                # Delete old file if it exists
                if existing_pdf.pdf_file:
                    try:
                        if existing_pdf.pdf_file.storage.exists(existing_pdf.pdf_file.name):
                            existing_pdf.pdf_file.delete(save=False)
                    except Exception as e:
                        print(f"Error deleting old PDF file: {str(e)}")
                
                # Save new file
                with open(pdf_path, 'rb') as f:
                    existing_pdf.pdf_file.save(filename, File(f), save=False)
                
                existing_pdf.filename = filename
                existing_pdf.source_type = source_type
                existing_pdf.metadata = metadata
                existing_pdf.save()
                
                return existing_pdf, False
            
            else:
                # Create new record
                print(f"Creating new PDF record for order {order_id}")
                
                order_pdf = OrderPDF(
                    order_id=order_id,
                    filename=filename,
                    source_type=source_type,
                    metadata=metadata
                )
                
                # Save the file
                with open(pdf_path, 'rb') as f:
                    order_pdf.pdf_file.save(filename, File(f), save=False)
                
                order_pdf.save()
                
                return order_pdf, True
                
    except FileNotFoundError as e:
        print(f"File not found error: {str(e)}")
        raise
    except Exception as e:
        print(f"Error saving PDF to database: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


def get_pdf_url(order_id):
    """
    Get the URL for a PDF file by order ID.
    
    Args:
        order_id (str): The order ID
    
    Returns:
        str or None: PDF URL if found, None otherwise
    """
    try:
        pdf_record = OrderPDF.objects.filter(order_id=order_id).first()
        if pdf_record and pdf_record.pdf_file:
            return pdf_record.pdf_file.url
        return None
    except Exception as e:
        print(f"Error getting PDF URL: {str(e)}")
        return None


def delete_pdf(order_id):
    """
    Delete a PDF file and its database record.
    
    Args:
        order_id (str): The order ID
    
    Returns:
        bool: True if deleted, False if not found
    """
    try:
        pdf_record = OrderPDF.objects.filter(order_id=order_id).first()
        if pdf_record:
            pdf_record.delete()  # Uses overridden delete() method to remove file
            print(f"Deleted PDF for order {order_id}")
            return True
        return False
    except Exception as e:
        print(f"Error deleting PDF: {str(e)}")
        return False


def cleanup_orphaned_pdfs():
    """
    Clean up PDF files that exist on disk but have no database record.
    Use with caution - run during maintenance windows.
    
    Returns:
        dict: Summary of cleanup operation
    """
    try:
        order_pdfs_dir = Path(settings.MEDIA_ROOT) / 'order_pdfs'
        
        if not order_pdfs_dir.exists():
            return {
                'status': 'success',
                'message': 'order_pdfs directory does not exist',
                'files_deleted': 0
            }
        
        # Get all order IDs from database
        db_order_ids = set(OrderPDF.objects.values_list('order_id', flat=True))
        
        # Get all PDF files from disk
        pdf_files = list(order_pdfs_dir.glob('*.pdf'))
        
        orphaned_files = []
        for pdf_file in pdf_files:
            # Extract order_id from filename (assuming format: order_ID.pdf or similar)
            # Adjust this logic based on your actual filename format
            if pdf_file.stem not in db_order_ids:
                orphaned_files.append(pdf_file)
        
        # Delete orphaned files
        deleted_count = 0
        for orphaned_file in orphaned_files:
            try:
                orphaned_file.unlink()
                deleted_count += 1
                print(f"Deleted orphaned file: {orphaned_file.name}")
            except Exception as e:
                print(f"Error deleting {orphaned_file.name}: {str(e)}")
        
        return {
            'status': 'success',
            'message': f'Cleanup completed',
            'total_files_on_disk': len(pdf_files),
            'orphaned_files_found': len(orphaned_files),
            'files_deleted': deleted_count
        }
        
    except Exception as e:
        print(f"Error in cleanup_orphaned_pdfs: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'message': str(e),
            'files_deleted': 0
        }