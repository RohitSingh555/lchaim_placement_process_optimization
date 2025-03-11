from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator

from private_healthcare_placement_optimization.enums import DocumentStatus

def document_upload_path(instance, filename):
    return f"documents/{instance.profile.user.id}/{filename}"

class PlacementProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="placement_profile")
    college_email = models.EmailField(unique=True, validators=[
        RegexValidator(regex=r"^[a-zA-Z0-9_.+-]+@peakcollege\.ca$", message="Must use @peakcollege.ca email")
    ])
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    # New Address Fields
    apt_house_no = models.CharField(max_length=255, null=True)
    street = models.CharField(max_length=255, null=True)
    city = models.CharField(max_length=100, null=True)
    province = models.CharField(max_length=100, null=True)
    postal_code = models.CharField(max_length=20, null=True)

    # New Field
    open_to_outside_city = models.BooleanField(default=False)

    experience_level = models.CharField(
        max_length=50,
        choices=[
            ("No Experience", "No Experience (300 Hrs)"),
            ("1 Year PSW Experience", "One Year PSW Experience (230 Hrs)"),
            ("International Nurse", "International Nurse (200 Hrs)"),
        ]
    )
    employer_letter = models.FileField(upload_to="documents/employer_letters/", null=True, blank=True)
    shift_requested = models.CharField(
        max_length=50,
        choices=[
            ("Morning", "Morning - Mon to Fri - 7AM to 3PM"),
            ("Evening", "Evening - Mon to Fri - 3PM to 11PM"),
            ("Night", "Night - Mon to Fri - 11PM to 7AM"),
            ("Weekend Morning", "Weekend Morning - Sat & Sun"),
            ("Weekend Evening", "Weekend Evening - Sat & Sun"),
            ("Weekend Night", "Weekend Night - Sat & Sun"),
        ]
    )
    preferred_facility_name = models.CharField(max_length=255, blank=True, null=True)
    preferred_facility_address = models.TextField(blank=True, null=True)
    preferred_facility_contact_person = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Document(models.Model):
    profile = models.ForeignKey(PlacementProfile, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(
        max_length=50,
        choices=[
            ("Medical Certificate", "Medical Certificate"),
            ("Covid Vaccination Certificate", "Covid Vaccination Certificate"),
            ("Vulnerable Sector Check", "Vulnerable Sector Check"),
            ("CPR or First Aid", "CPR or First Aid"),
            ("Mask Fit Certificate", "Mask Fit Certificate"),
            ("Basic Life Support", "Basic Life Support"),
        ]
    )
    file = models.FileField(upload_to=document_upload_path)
    status = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices(),
        default=DocumentStatus.IN_REVIEW.value
    )
    rejection_reason = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

class Approver(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="approver_profile")
    full_name = models.CharField(max_length=255)
    position = models.CharField(max_length=255)

class ApprovalLog(models.Model):
    approver = models.ForeignKey(Approver, on_delete=models.SET_NULL, null=True)
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    action = models.CharField(max_length=10, choices=[("Approved", "Approved"), ("Rejected", "Rejected")])
    reason = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

class FeeStatus(models.Model):
    profile = models.OneToOneField(PlacementProfile, on_delete=models.CASCADE, related_name="fee_status")
    is_paid = models.BooleanField(default=False)
    last_reminder_sent = models.DateTimeField(null=True, blank=True)
    payment_due_date = models.DateField(null=True, blank=True)
    reminder_count = models.IntegerField(default=0)

class PlacementNotification(models.Model):
    profile = models.ForeignKey(PlacementProfile, on_delete=models.CASCADE, related_name="notifications")
    subject = models.CharField(max_length=255)
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
