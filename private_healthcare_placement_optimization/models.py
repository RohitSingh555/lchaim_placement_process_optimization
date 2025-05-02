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
    city_preference_1 = models.CharField(max_length=100, null=True, blank=True)
    city_preference_2 = models.CharField(max_length=100, null=True, blank=True)
    preferred_facility_contact_person = models.CharField(max_length=100, blank=True, null=True)
    assigned_facility = models.ForeignKey('Facility', on_delete=models.SET_NULL, null=True, blank=True)
    orientation_date = models.ForeignKey('OrientationDate', on_delete=models.SET_NULL, null=True, blank=True)
    #new fields
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_profiles')
    
    stage = models.CharField(
        max_length=30,
        choices=[
            ("DONE", "Done"),
            ("ENDORSED", "Endorsed"),
            ("IN_PLACEMENT", "In Placement"),
            ("CANCELLED", "Cancelled"),
            ("TRANSFERED", "Transferred"),
            ("ONHOLD", "On Hold"),
            ("ONGOING_PROCESS", "Ongoing Process"),
            ("ORIENTATION_SCHEDULED", "Orientation Scheduled"),
            ("READY", "Ready"),
        ],
        null=True,
        blank=True
    )
    official_start_date = models.DateField(null=True, blank=True)
    exact_placement_end_date = models.DateField(null=True, blank=True)
    facility_feedback = models.TextField(null=True, blank=True)
    college_feedback = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    date_completed = models.DateField(null=True, blank=True)
    required_hours = models.PositiveIntegerField(default=300, null=True, blank=True)
    time_period = models.CharField(max_length=100, null=True, blank=True)
    days = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    module_completed = models.BooleanField(default=False)
    pregnancy_waiver_check = models.BooleanField(default=False)
    gender = models.CharField(
        max_length=20,
        choices=[
            ("Male", "Male"),
            ("Female", "Female"),
            ("Other", "Other"),
            ("Prefer not to say", "Prefer not to say")
        ],
        null=True,
        blank=True
    )

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
    file_name = models.CharField(max_length=255, blank=True, null=True)
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

class StudentID(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_id_record')
    student_id = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return f"{self.user.username} - {self.student_id}"
    
class Facility(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
    ]

    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    province = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    address = models.TextField()
    facility_phone = models.CharField(max_length=20, blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    person_in_charge = models.CharField(max_length=100)
    email = models.EmailField()
    phone_number = models.CharField(max_length=20)
    designation = models.CharField(max_length=100)

    additional_requirements = models.TextField(blank=True, null=True)
    shifts_available = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-created_at']


class OrientationDate(models.Model):
    orientation_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.orientation_date.strftime("%B %d, %Y")

    class Meta:
        ordering = ['-orientation_date']

class City(models.Model):
    name = models.CharField(max_length=100)
    province = models.CharField(max_length=100)

    class Meta:
        unique_together = ('name', 'province')  # allow same city name in different provinces
