from django.db import models
import os
from uuid import uuid4
from django.contrib.auth.models import User
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

class PicklistDispatchStatus(models.Model):
    """
    Model to track which picklists have orders in Dispatch status
    """
    picklist = models.OneToOneField(Picklist, on_delete=models.CASCADE, related_name='dispatch_status')
    total_orders = models.IntegerField(default=0)
    dispatched_orders = models.IntegerField(default=0)
    is_fully_dispatched = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Picklist Dispatch Status"
        verbose_name_plural = "Picklist Dispatch Statuses"
    
    def __str__(self):
        percentage = 0
        if self.total_orders > 0:
            percentage = (self.dispatched_orders / self.total_orders) * 100
        
        return f"{self.picklist.picklist_id}: {self.dispatched_orders}/{self.total_orders} ({percentage:.1f}% dispatched)"
    
    def update_status(self):
        """
        Update the dispatch counts and status by checking all orders in the picklist
        """
        platform = self.picklist.platform
        picklist_items = PicklistItem.objects.filter(picklist=self.picklist)
        order_numbers = picklist_items.values_list('order_number', flat=True).distinct()
        
        self.total_orders = len(order_numbers)
        self.dispatched_orders = 0
        
        # Count dispatched orders based on platform
        for order_num in order_numbers:
            is_dispatched = False
            
            if platform == 'AMAZON':
                is_dispatched = AmazonOrders.objects.filter(order_number=order_num, status='Dispatch').exists()
            elif platform == 'FLIPKART':
                is_dispatched = FlipkarOrders.objects.filter(order_number=order_num, status='Dispatch').exists()
            elif platform == 'FIRSTCRY':
                is_dispatched = FirstcryOrders.objects.filter(order_number=order_num, status='Dispatch').exists()
            elif platform == 'MEESHO':
                is_dispatched = MeeshoOrders.objects.filter(order_number=order_num, status='Dispatch').exists()
            
            if is_dispatched:
                self.dispatched_orders += 1
        
        self.is_fully_dispatched = (self.dispatched_orders == self.total_orders) and (self.total_orders > 0)
        
        # If all orders are dispatched, update the picklist status to "DISPATCH"
        if self.is_fully_dispatched and self.picklist.status != 'DISPATCH':
            self.picklist.status = 'DISPATCH'
            self.picklist.save()
        
        self.save()
        return self.is_fully_dispatched
    
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