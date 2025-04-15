from django.db import models
import os
from uuid import uuid4
from django.contrib.auth.models import User

class PDFUpload(models.Model):
    title = models.CharField(max_length=255, blank=True)  # Allow blank, will be auto-set
    file = models.FileField(upload_to='uploads/pdfs/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.title:  # Only set title if it's not manually provided
            self.title = os.path.basename(self.file.name)  # Extract file name
        super().save(*args, **kwargs)  # Call the parent save method

    def __str__(self):
        return self.title
    

class AmazonOrders(models.Model):
    order_number = models.CharField(max_length=200)
    sku = models.CharField(max_length=200)
    quantity = models.IntegerField()
    order_type = models.CharField(max_length=200,default="Single")
    status = models.CharField(max_length=200,default="Ready to Process")
    pdf_url = models.CharField(max_length=300)
    AWB = models.CharField(max_length=100)

    def __str__(self):
        return f"Order {self.order_number}"

class FlipkarOrders(models.Model):
    order_number = models.CharField(max_length=200)
    sku = models.CharField(max_length=200)
    quantity = models.IntegerField()
    order_type = models.CharField(max_length=200,default="Single")
    status = models.CharField(max_length=200,default="Ready to Process")
    pdf_url = models.CharField(max_length=300)
    AWB = models.CharField(max_length=100)

    def __str__(self):
        return f"Order {self.order_number}"
    
class FirstcryOrders(models.Model):
    order_number = models.CharField(max_length=200)
    sku = models.CharField(max_length=200)
    quantity = models.IntegerField()
    order_type = models.CharField(max_length=200,default="Single")
    status = models.CharField(max_length=200,default="Ready to Process")
    pdf_url = models.CharField(max_length=300)
    AWB = models.CharField(max_length=100)

    def __str__(self):
        return f"Order {self.order_number}"
    
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
        # Create a unique constraint for SKU and location combination
        unique_together = ('sku', 'location')
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['location']),
            models.Index(fields=['product_id']),
        ]
    
    def __str__(self):
        return f"{self.sku} - {self.location}"
        
# Add to models.py
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
        # Get the latest picklist ID or start with 111001
        latest_picklist = cls.objects.order_by('-picklist_id').first()
        if latest_picklist:
            try:
                # Try to convert the latest ID to an integer and increment it
                latest_id = int(latest_picklist.picklist_id)
                return str(latest_id + 1)
            except (ValueError, TypeError):
                # If conversion fails, start with 111002
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

# If you're using Django signals, you might want to create a profile automatically
# when a new user is created
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if not hasattr(instance, 'profile'):
        UserProfile.objects.create(user=instance)
    instance.profile.save()