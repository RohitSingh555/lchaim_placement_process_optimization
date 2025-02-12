from django import forms
from .models import PlacementProfile, Document, User
from django.contrib.auth.forms import UserCreationForm

class PlacementProfileForm(forms.ModelForm):
    class Meta:
        model = PlacementProfile
        fields = ['college_email', 'first_name', 'last_name', 'address_updated', 'experience_level', 
                  'employer_letter', 'shift_requested', 'preferred_facility_name', 'preferred_facility_address', 
                  'preferred_facility_contact_person']

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
        fields = ("username", "email", "password1", "password2")