"""
Management command to delete old PDF files and records.
Run this periodically via cron job or task scheduler.

Usage:
    python manage.py cleanup_old_pdfs --hours=10
    python manage.py cleanup_old_pdfs --hours=10 --dry-run
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from pathlib import Path
import os

from ordercycle.models import OrderPDF, PDFUpload


class Command(BaseCommand):
    help = 'Delete PDF files and records older than specified hours'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=10,
            help='Delete PDFs older than this many hours (default: 10)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output for each file deleted'
        )

    def handle(self, *args, **options):
        hours = options['hours']
        dry_run = options['dry_run']
        verbose = options['verbose']
        
        cutoff_time = timezone.now() - timedelta(hours=hours)
        
        self.stdout.write(
            self.style.WARNING(
                f"{'[DRY RUN] ' if dry_run else ''}Deleting PDFs older than {hours} hours "
                f"(before {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')})"
            )
        )
        
        # Cleanup OrderPDF records
        order_pdf_deleted = self._cleanup_order_pdfs(cutoff_time, dry_run, verbose)
        
        # Cleanup PDFUpload records
        pdf_upload_deleted = self._cleanup_pdf_uploads(cutoff_time, dry_run, verbose)
        
        # Summary
        total_deleted = order_pdf_deleted + pdf_upload_deleted
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'[DRY RUN] Would delete' if dry_run else 'Deleted'} "
                f"{total_deleted} PDF records total:\n"
                f"  - OrderPDF: {order_pdf_deleted}\n"
                f"  - PDFUpload: {pdf_upload_deleted}"
            )
        )

    def _cleanup_order_pdfs(self, cutoff_time, dry_run, verbose):
        """Delete OrderPDF records older than cutoff time."""
        old_pdfs = OrderPDF.objects.filter(created_at__lt=cutoff_time)
        count = old_pdfs.count()
        
        if count == 0:
            self.stdout.write("No old OrderPDF records to delete")
            return 0
        
        self.stdout.write(f"\nFound {count} old OrderPDF records")
        
        if not dry_run:
            deleted_count = 0
            
            # Delete files from file system first
            for pdf_record in old_pdfs:
                if pdf_record.pdf_file:
                    try:
                        # Delete the physical file
                        if pdf_record.pdf_file.storage.exists(pdf_record.pdf_file.name):
                            pdf_record.pdf_file.delete(save=False)
                            if verbose:
                                self.stdout.write(f"  Deleted file: {pdf_record.pdf_file.name}")
                            deleted_count += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"  Error deleting file {pdf_record.pdf_file.name}: {str(e)}")
                        )
            
            # Delete all database records
            db_deleted = old_pdfs.delete()[0]
            self.stdout.write(self.style.SUCCESS(f"Deleted {db_deleted} OrderPDF database records"))
            return deleted_count
        
        return count

    def _cleanup_pdf_uploads(self, cutoff_time, dry_run, verbose):
        """Delete PDFUpload records older than cutoff time."""
        old_uploads = PDFUpload.objects.filter(uploaded_at__lt=cutoff_time)
        count = old_uploads.count()
        
        if count == 0:
            self.stdout.write("No old PDFUpload records to delete")
            return 0
        
        self.stdout.write(f"\nFound {count} old PDFUpload records")
        
        if not dry_run:
            deleted_count = 0
            
            # Delete files from file system first
            for upload in old_uploads:
                if upload.file:
                    try:
                        # Delete the physical file
                        if upload.file.storage.exists(upload.file.name):
                            upload.file.delete(save=False)
                            if verbose:
                                self.stdout.write(f"  Deleted file: {upload.file.name}")
                            deleted_count += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"  Error deleting file {upload.file.name}: {str(e)}")
                        )
            
            # Delete all database records
            db_deleted = old_uploads.delete()[0]
            self.stdout.write(self.style.SUCCESS(f"Deleted {db_deleted} PDFUpload database records"))
            return deleted_count
        
        return count