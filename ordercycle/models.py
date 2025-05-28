from django.db import models
import os
from uuid import uuid4
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.files.base import ContentFile
import base64

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
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['order_number', 'status']),
            models.Index(fields=['order_type', 'status']),
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
        ('COMPLETED', 'Completed'),
    ]
    
    picklist_id = models.CharField(max_length=10, unique=True)
    picklist_type = models.CharField(max_length=10, choices=PICKLIST_TYPE_CHOICES)
    quantity = models.IntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='CREATED')
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
        Get validation status for all SKUs in this picklist
        """
        # Get all unique SKU-Order combinations in this picklist
        picklist_items = PicklistItem.objects.filter(picklist=self)
        total_skus = picklist_items.values('sku', 'order_number').distinct().count()
        
        # Ensure validation records exist for all SKUs
        for item in picklist_items.values('sku', 'order_number').distinct():
            PicklistSKUValidation.objects.get_or_create(
                picklist=self,
                sku=item['sku'],
                order_number=item['order_number'],
                defaults={'validated': False}
            )
        
        # Count validated SKUs
        validated_count = PicklistSKUValidation.objects.filter(
            picklist=self, 
            validated=True
        ).count()
        
        return {
            'total_skus': total_skus,
            'validated_count': validated_count,
            'all_validated': validated_count == total_skus and total_skus > 0
        }

    def get_order_validation_status(self, order_number):
        """
        Get validation status for a specific order in this picklist
        """
        # Get all SKUs for this order in this picklist
        order_skus = PicklistItem.objects.filter(
            picklist=self, 
            order_number=order_number
        ).values('sku').distinct()
        
        total_order_skus = order_skus.count()
        
        # Ensure validation records exist for all SKUs in this order
        for item in order_skus:
            PicklistSKUValidation.objects.get_or_create(
                picklist=self,
                sku=item['sku'],
                order_number=order_number,
                defaults={'validated': False}
            )
        
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
    # Primary key field using order_id
    order_id = models.CharField(max_length=100, primary_key=True)
    
    # Store the PDF content directly in PostgreSQL
    pdf_content = models.BinaryField()
    
    # Additional metadata
    filename = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    source_type = models.CharField(max_length=50, default="unknown")  # To track which script processed this
    
    # Store additional info as JSON
    metadata = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"Order {self.order_id}"
        
    class Meta:
        indexes = [
            models.Index(fields=['created_at']),
        ]

class PicklistSKUValidation(models.Model):
    """
    Model to track which SKUs have been validated for each picklist
    """
    picklist = models.ForeignKey(Picklist, on_delete=models.CASCADE, related_name='sku_validations')
    sku = models.CharField(max_length=200, db_index=True)
    order_number = models.CharField(max_length=200, db_index=True)
    validated = models.BooleanField(default=False)
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        unique_together = ('picklist', 'sku', 'order_number')
        indexes = [
            models.Index(fields=['picklist', 'sku']),
            models.Index(fields=['picklist', 'validated']),
            models.Index(fields=['order_number', 'validated']),
        ]
    
    def __str__(self):
        return f"SKU {self.sku} in {self.picklist.picklist_id} - Order: {self.order_number} - Validated: {self.validated}"