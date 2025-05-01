from django import forms
from .models import Facility, OrientationDate, PlacementProfile, Document, StudentID, User
from django.contrib.auth.forms import UserCreationForm

ALLOWED_EMAIL_DOMAIN ="@peakcollege.ca"

class PlacementProfileForm(forms.ModelForm):
    class Meta:
        model = PlacementProfile
        fields = [
            'college_email', 'first_name', 'last_name',  
            'apt_house_no', 'street', 'city', 'province', 'postal_code',  # New address fields
            'open_to_outside_city',  # New placement question field
            'experience_level', 'employer_letter', 'shift_requested', 
            'preferred_facility_name', 'preferred_facility_address', 'preferred_facility_contact_person'
        ]

    def clean_college_email(self):
        email = self.cleaned_data['college_email']
        if not email.endswith("@peakcollege.ca"):
            raise forms.ValidationError("Email must end with @peakcollege.ca")
        return email


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['document_type', 'file']
    
    def clean_file(self):
        file = self.cleaned_data['file']
        allowed_extensions = ['pdf', 'jpg', 'jpeg', 'png']
        if not any(file.name.lower().endswith(ext) for ext in allowed_extensions):
            raise forms.ValidationError("Only PDF, JPG, and PNG files are allowed.")
        return file

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add custom classes to each form field
        self.fields['username'].widget.attrs.update({
            'class': 'block w-full px-4 py-2 mt-1 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500'
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'block w-full px-4 py-2 mt-1 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'block w-full px-4 py-2 mt-1 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500'
        })
        
class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="College Email")
    student_id = forms.CharField(required=True, label="Student ID")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "student_id", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not email.endswith("@peakcollege.ca"):
            raise forms.ValidationError("Email must be a valid Peak College email (@peakcollege.ca).")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_student_id(self):
        student_id = self.cleaned_data.get("student_id")
        if StudentID.objects.filter(student_id=student_id).exists():
            raise forms.ValidationError("This student ID is already taken.")
        return student_id

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email
        if commit:
            user.save()
            # Save student ID
            StudentID.objects.create(user=user, student_id=self.cleaned_data["student_id"])
        return user
    
class FacilityForm(forms.ModelForm):
    class Meta:
        model = Facility
        fields = '__all__'

class OrientationDateForm(forms.ModelForm):
    class Meta:
        model = OrientationDate
        fields = ['orientation_date']