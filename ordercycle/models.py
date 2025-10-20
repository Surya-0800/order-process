from django.db import models
import os
from uuid import uuid4
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.files.base import ContentFile
import base64
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver

class PDFUpload(models.Model):
    title = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to='uploads/pdfs/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.title:
            self.title = os.path.basename(self.file.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
    
# Base Order model to reduce code duplication
class BaseOrder(models.Model):
    order_number = models.CharField(max_length=200, db_index=True)
    sku = models.CharField(max_length=200, db_index=True)
    quantity = models.IntegerField()
    order_type = models.CharField(max_length=200, default="Single")
    status = models.CharField(max_length=200, default="Ready to Process", db_index=True)
    pdf_url = models.CharField(max_length=300)
    AWB = models.CharField(max_length=100, blank=True, null=True)
    
    # NEW FIELDS - Add these:
    is_printed = models.BooleanField(default=False, help_text="Whether the order has been printed")
    printed_at = models.DateTimeField(null=True, blank=True, help_text="When the order was printed")
    is_validated = models.BooleanField(default=False, help_text="Whether AWB has been validated")
    validated_at = models.DateTimeField(null=True, blank=True, help_text="When AWB was validated")
    processed_at = models.DateTimeField(null=True, blank=True, help_text="When order was marked as processed")
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['order_number', 'status']),
            models.Index(fields=['order_type', 'status']),
            # NEW INDEXES:
            models.Index(fields=['is_printed', 'is_validated']),
            models.Index(fields=['status', 'is_validated']),
        ]

    def __str__(self):
        return f"Order {self.order_number}"
class AmazonOrders(BaseOrder):
    class Meta:
        verbose_name = "Amazon Order"
        verbose_name_plural = "Amazon Orders"

class FlipkarOrders(BaseOrder):
    class Meta:
        verbose_name = "Flipkart Order"
        verbose_name_plural = "Flipkart Orders"
    
class FirstcryOrders(BaseOrder):
    class Meta:
        verbose_name = "FirstCry Order"
        verbose_name_plural = "FirstCry Orders"
    
class MeeshoOrders(BaseOrder):
    class Meta:
        verbose_name = "Meesho Order"
        verbose_name_plural = "Meesho Orders"
    
class MasterTable(models.Model):
    sku = models.CharField(max_length=100, db_index=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)
    location = models.CharField(max_length=50, db_index=True)
    product_id = models.CharField(max_length=100, null=True, blank=True)
    box_no = models.CharField(max_length=50, null=True, blank=True)
    mrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    generic_name = models.CharField(max_length=255, null=True, blank=True)
    pack_check = models.CharField(max_length=100, null=True, blank=True)
    pack_remarks = models.TextField(null=True, blank=True)
    
    class Meta:
        unique_together = ('sku', 'location')
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['location']),
            models.Index(fields=['product_id']),
        ]
    
    def __str__(self):
        return f"{self.sku} - {self.location}"
        
class Picklist(models.Model):
    PICKLIST_TYPE_CHOICES = [
        ('SINGLE', 'Single'),
        ('MULTI', 'Multi'),
    ]
    
    STATUS_CHOICES = [
        ('CREATED', 'Created'),
        ('PRINTED', 'Printed'),
        ('PACKING', 'Packing'),
        ('PARTIAL_DISPATCH', 'Partial Dispatch'),
        ('DISPATCH', 'Dispatch'),                   
    ]
    
    picklist_id = models.CharField(max_length=10, unique=True)
    picklist_type = models.CharField(max_length=10, choices=PICKLIST_TYPE_CHOICES)
    quantity = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CREATED')  # Increased max_length
    platform = models.CharField(max_length=20)  # AMAZON, FLIPKART, FIRSTCRY, MEESHO
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Picklist {self.picklist_id} ({self.picklist_type})"
    
    @classmethod
    def generate_picklist_id(cls):
        latest_picklist = cls.objects.order_by('-picklist_id').first()
        if latest_picklist:
            try:
                latest_id = int(latest_picklist.picklist_id)
                return str(latest_id + 1)
            except (ValueError, TypeError):
                return "111002"
        return "111002"  # First picklist ID
    
    def get_validation_status(self):
        """
        Enhanced validation status that considers quantity vs validated count
        """
        # Get all unique SKU-Order combinations in this picklist
        picklist_items = PicklistItem.objects.filter(picklist=self)
        
        # Ensure validation records exist for all SKUs with correct quantities and product_ids
        for item in picklist_items.values('sku', 'order_number', 'quantity').distinct():
            # Get product_id from master table
            product = MasterTable.objects.filter(sku=item['sku']).first()
            product_id = product.product_id if product else None
            
            validation_record, created = PicklistSKUValidation.objects.get_or_create(
                picklist=self,
                sku=item['sku'],
                order_number=item['order_number'],
                defaults={
                    'validated': False,
                    'quantity': item['quantity'],
                    'validated_count': 0,
                    'product_id': product_id
                }
            )
            
            # Update existing records that might not have quantity/product_id
            if not created and (validation_record.quantity != item['quantity'] or not validation_record.product_id):
                validation_record.quantity = item['quantity']
                validation_record.product_id = product_id
                # Recalculate validated status based on count vs quantity
                validation_record.validated = validation_record.validated_count >= validation_record.quantity
                validation_record.save()
        
        # Count total and validated SKUs
        all_validations = PicklistSKUValidation.objects.filter(picklist=self)
        total_skus = all_validations.count()
        validated_count = all_validations.filter(validated=True).count()
        
        return {
            'total_skus': total_skus,
            'validated_count': validated_count,
            'all_validated': validated_count == total_skus and total_skus > 0
        }

    def get_order_validation_status(self, order_number):
        """
        Enhanced order validation status that considers quantity vs validated count
        """
        # Get all SKUs for this order in this picklist
        order_items = PicklistItem.objects.filter(
            picklist=self, 
            order_number=order_number
        ).values('sku', 'quantity').distinct()
        
        total_order_skus = order_items.count()
        
        # Ensure validation records exist for all SKUs in this order
        for item in order_items:
            # Get product_id from master table
            product = MasterTable.objects.filter(sku=item['sku']).first()
            product_id = product.product_id if product else None
            
            validation_record, created = PicklistSKUValidation.objects.get_or_create(
                picklist=self,
                sku=item['sku'],
                order_number=order_number,
                defaults={
                    'validated': False,
                    'quantity': item['quantity'],
                    'validated_count': 0,
                    'product_id': product_id
                }
            )
            
            # Update existing records
            if not created and (validation_record.quantity != item['quantity'] or not validation_record.product_id):
                validation_record.quantity = item['quantity']
                validation_record.product_id = product_id
                validation_record.validated = validation_record.validated_count >= validation_record.quantity
                validation_record.save()
        
        # Count validated SKUs for this order
        validated_order_skus = PicklistSKUValidation.objects.filter(
            picklist=self,
            order_number=order_number,
            validated=True
        ).count()
        
        return {
            'total_skus': total_order_skus,
            'validated_count': validated_order_skus,
            'all_validated': validated_order_skus == total_order_skus and total_order_skus > 0
        }


class PicklistItem(models.Model):
    picklist = models.ForeignKey(Picklist, on_delete=models.CASCADE, related_name='items')
    order_number = models.CharField(max_length=200)
    sku = models.CharField(max_length=200)
    quantity = models.IntegerField()
    picked = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Item {self.sku} in {self.picklist}"
    
class Picker(models.Model):
    picker_id = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Picker {self.picker_id}: {self.name}"

class PicklistItemLocation(models.Model):
    picklist_item = models.OneToOneField(PicklistItem, on_delete=models.CASCADE, related_name='location_info')
    location = models.CharField(max_length=50)
    picked = models.BooleanField(default=False)
    picker = models.ForeignKey(Picker, on_delete=models.SET_NULL, null=True, blank=True, related_name='picked_items')
    picked_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Location {self.location} for {self.picklist_item}"

class UserProfile(models.Model):
    """
    Extended user profile model to store additional user-specific data
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    printer_preference = models.CharField(max_length=255, blank=True, null=True)
    label_printer_preference = models.CharField(max_length=255, blank=True, null=True)
    default_print_settings = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if not hasattr(instance, 'profile'):
        UserProfile.objects.create(user=instance)
    instance.profile.save()

# Add this to your models.py file

# Enhanced PicklistDispatchStatus model in models.py

class PicklistDispatchStatus(models.Model):
    """
    Model to track dispatch workflow for picklists
    Tracks orders in Complete (ready to dispatch) and Dispatch (already dispatched) status
    """
    picklist = models.OneToOneField(Picklist, on_delete=models.CASCADE, related_name='dispatch_status')
    total_orders = models.IntegerField(default=0)  # Total orders in this picklist
    dispatched_orders = models.IntegerField(default=0)  # Orders in 'Dispatch' status
    complete_orders = models.IntegerField(default=0)  # Orders in 'Complete' status (ready to dispatch)
    total_relevant_orders = models.IntegerField(default=0)  # Complete + Dispatch orders
    is_fully_dispatched = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Picklist Dispatch Status"
        verbose_name_plural = "Picklist Dispatch Statuses"
    
    def __str__(self):
        dispatch_percentage = 0
        if self.total_orders > 0:
            dispatch_percentage = (self.dispatched_orders / self.total_orders) * 100
        
        return f"{self.picklist.picklist_id}: {self.dispatched_orders}/{self.total_orders} ({dispatch_percentage:.1f}% dispatched) | {self.complete_orders} ready"
    
    def update_status(self):
        """
        Legacy method - just calls the enhanced version
        """
        return self.update_status_with_complete_and_dispatch()
    
    def update_status_with_complete_and_dispatch(self):
        """
        Update counts for both Complete and Dispatch orders
        """
        platform = self.picklist.platform.upper()
        picklist_items = PicklistItem.objects.filter(picklist=self.picklist)
        order_numbers = picklist_items.values_list('order_number', flat=True).distinct()
        
        self.total_orders = len(order_numbers)
        self.dispatched_orders = 0
        self.complete_orders = 0
        
        # Count orders in both Complete and Dispatch status
        for order_num in order_numbers:
            order_status = None
            
            if platform == 'AMAZON':
                order = AmazonOrders.objects.filter(order_number=order_num).first()
            elif platform == 'FLIPKART':
                order = FlipkarOrders.objects.filter(order_number=order_num).first()
            elif platform == 'FIRSTCRY':
                order = FirstcryOrders.objects.filter(order_number=order_num).first()
            elif platform == 'MEESHO':
                order = MeeshoOrders.objects.filter(order_number=order_num).first()
            
            if order:
                if order.status == 'Dispatch':
                    self.dispatched_orders += 1
                elif order.status == 'Complete':
                    self.complete_orders += 1
        
        # Calculate totals
        self.total_relevant_orders = self.dispatched_orders + self.complete_orders
        self.is_fully_dispatched = (self.dispatched_orders == self.total_orders) and (self.total_orders > 0)
        
        self.save()
        return self.is_fully_dispatched
    
    def get_dispatch_summary(self):
        """
        Get a summary of the dispatch status for this picklist
        """
        dispatch_percentage = 0
        complete_percentage = 0
        
        if self.total_orders > 0:
            dispatch_percentage = (self.dispatched_orders / self.total_orders) * 100
            complete_percentage = (self.complete_orders / self.total_orders) * 100
        
        return {
            'picklist_id': self.picklist.picklist_id,
            'platform': self.picklist.platform,
            'total_orders': self.total_orders,
            'dispatched_orders': self.dispatched_orders,
            'complete_orders': self.complete_orders,
            'total_relevant_orders': self.total_relevant_orders,
            'dispatch_percentage': round(dispatch_percentage, 1),
            'complete_percentage': round(complete_percentage, 1),
            'is_fully_dispatched': self.is_fully_dispatched,
            'has_orders_to_process': self.complete_orders > 0,
            'workflow_status': self._get_workflow_status()
        }
    
    def _get_workflow_status(self):
        """
        Get a human-readable workflow status
        """
        if self.total_relevant_orders == 0:
            return "No orders ready for dispatch"
        elif self.is_fully_dispatched:
            return "Fully dispatched"
        elif self.dispatched_orders > 0 and self.complete_orders > 0:
            return "Partially dispatched"
        elif self.dispatched_orders == 0 and self.complete_orders > 0:
            return "Ready to dispatch"
        else:
            return "In progress"
        
import uuid
class ImageUpload(models.Model):
    """
    Model for storing uploaded images in PostgreSQL database.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, blank=True)
    file_name = models.CharField(max_length=255)
    image = models.BinaryField()  # Store image as binary data in PostgreSQL
    content_type = models.CharField(max_length=100)  # Store MIME type
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # Optional: Add a field to link to a product if needed
    # product = models.ForeignKey('Product', on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        verbose_name = "Image Upload"
        verbose_name_plural = "Image Uploads"
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return self.file_name or str(self.id)
    
class OrderPDF(models.Model):
    """
    Stores order PDFs on file system for performance.
    PDFs are automatically cleaned up after 8-12 hours.
    """
    order_id = models.CharField(max_length=255, unique=True, db_index=True, primary_key=True)
    
    # CHANGED: From BinaryField to FileField
    pdf_file = models.FileField(upload_to='order_pdfs/', null=True, blank=True)
    
    filename = models.CharField(max_length=255)
    source_type = models.CharField(max_length=50, default='upload')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Order PDF"
        verbose_name_plural = "Order PDFs"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"PDF for Order {self.order_id}"
    
    @property
    def pdf_url(self):
        """Get the URL for the PDF file."""
        if self.pdf_file:
            return self.pdf_file.url
        return None
    
    def delete(self, *args, **kwargs):
        """Override delete to also remove the physical file."""
        if self.pdf_file:
            try:
                if self.pdf_file.storage.exists(self.pdf_file.name):
                    self.pdf_file.delete(save=False)
            except Exception as e:
                print(f"Error deleting PDF file: {str(e)}")
        super().delete(*args, **kwargs)

class PicklistSKUValidation(models.Model):
    """
    Enhanced model to track validation count vs required quantity for each SKU
    """
    picklist = models.ForeignKey(Picklist, on_delete=models.CASCADE, related_name='sku_validations')
    sku = models.CharField(max_length=200, db_index=True)
    order_number = models.CharField(max_length=200, db_index=True)
    product_id = models.CharField(max_length=100, blank=True, null=True)  # NEW: Product ID from master table
    quantity = models.IntegerField(default=1)  # NEW: Required quantity for this SKU in this order
    validated_count = models.IntegerField(default=0)  # NEW: How many times user has validated this SKU
    validated = models.BooleanField(default=False)  # True only when validated_count == quantity
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        unique_together = ('picklist', 'sku', 'order_number')
        indexes = [
            models.Index(fields=['picklist', 'sku']),
            models.Index(fields=['picklist', 'validated']),
            models.Index(fields=['order_number', 'validated']),
            models.Index(fields=['validated_count', 'quantity']),
        ]
    
    def __str__(self):
        return f"SKU {self.sku} in {self.picklist.picklist_id} - Order: {self.order_number} - Validated: {self.validated_count}/{self.quantity}"
    
    def is_fully_validated(self):
        """Check if this SKU is fully validated for this order"""
        return self.validated_count >= self.quantity
    
    def get_validation_progress(self):
        """Get validation progress as a dictionary"""
        return {
            'validated_count': self.validated_count,
            'required_quantity': self.quantity,
            'is_complete': self.is_fully_validated(),
            'percentage': (self.validated_count / self.quantity * 100) if self.quantity > 0 else 0
        }
    
    def increment_validation(self, user=None):
        """Increment validation count and update status"""
        if self.validated_count < self.quantity:
            self.validated_count += 1
            
            # Mark as validated only when count reaches quantity
            if self.validated_count >= self.quantity:
                self.validated = True
                self.validated_at = timezone.now()
                if user:
                    self.validated_by = user
            
            self.save()
            return True
        return False
    
@receiver(post_save, sender=PicklistItem)
def create_sku_validation_record(sender, instance, created, **kwargs):
    """
    Automatically create PicklistSKUValidation record when a PicklistItem is created
    """
    if created:  # Only run when a new PicklistItem is created
        try:
            # Get product_id from master table
            product = MasterTable.objects.filter(sku=instance.sku).first()
            product_id = product.product_id if product else None
            
            # Create or get validation record
            validation_record, validation_created = PicklistSKUValidation.objects.get_or_create(
                picklist=instance.picklist,
                sku=instance.sku,
                order_number=instance.order_number,
                defaults={
                    'validated': False,
                    'quantity': instance.quantity,
                    'validated_count': 0,
                    'product_id': product_id
                }
            )
            
            if validation_created:
                print(f"✅ Auto-created validation record for SKU {instance.sku} in order {instance.order_number}")
            else:
                # Update existing record if needed
                update_needed = False
                if validation_record.quantity != instance.quantity:
                    validation_record.quantity = instance.quantity
                    update_needed = True
                if not validation_record.product_id and product_id:
                    validation_record.product_id = product_id
                    update_needed = True
                    
                if update_needed:
                    validation_record.save()
                    print(f"🔄 Updated existing validation record for SKU {instance.sku}")
                    
        except Exception as e:
            print(f"❌ Error creating validation record for {instance.sku}: {str(e)}")
            # Don't raise the exception to avoid breaking picklist creation


@receiver(post_save, sender=PicklistItem)
def update_sku_validation_on_change(sender, instance, created, **kwargs):
    """
    Update validation record when PicklistItem quantity changes
    """
    if not created:  # Only run for updates, not creation
        try:
            validation_record = PicklistSKUValidation.objects.filter(
                picklist=instance.picklist,
                sku=instance.sku,
                order_number=instance.order_number
            ).first()
            
            if validation_record and validation_record.quantity != instance.quantity:
                validation_record.quantity = instance.quantity
                # Recalculate validated status based on new quantity
                validation_record.validated = validation_record.validated_count >= validation_record.quantity
                validation_record.save()
                print(f"🔄 Updated validation quantity for SKU {instance.sku}")
                
        except Exception as e:
            print(f"❌ Error updating validation record for {instance.sku}: {str(e)}")