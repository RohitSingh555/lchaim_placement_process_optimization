from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from .models import PlacementProfile, Document, Approver, ApprovalLog, FeeStatus, PlacementNotification
from .forms import PlacementProfileForm, DocumentForm
from django.core.mail import send_mail
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate, login, logout

def staff_required(view_func):
    return user_passes_test(lambda u: u.is_staff)(view_func)

@staff_required
def staff_only_view(request):
    return render(request, 'staff_page.html')

def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('login')
    else:
        form = UserCreationForm()

    return render(request, 'signup.html', {'form': form})

class StaffSignupView(View):
    def get(self, request, *args, **kwargs):
        # If access password is already correct (stored in session), show the form
        if request.session.get('password_verified', False):
            form = UserCreationForm()
            return render(request, 'staff_signup.html', {'form': form, 'password_verified': True})

        # If not, show password form
        return render(request, 'staff_signup.html', {'password_verified': False})

    def post(self, request, *args, **kwargs):
        # Handle password verification form
        if 'password' in request.POST:
            access_password = request.POST.get('password')
            if access_password == '1234':
                # Store the verification status in the session
                request.session['password_verified'] = True
                return redirect('staff_signup')  # Reload the page with the form visible
            else:
                return render(request, 'staff_signup.html', {'password_verified': False, 'error_message': 'Incorrect password.'})

        # Handle staff registration form submission
        if request.session.get('password_verified', False):
            form = UserCreationForm(request.POST)
            if form.is_valid():
                user = form.save()
                user.is_staff = True  # Set is_staff to True
                user.save()

                # After successful registration, redirect to login page
                return redirect('login')

        # If not verified, redirect to password entry form
        return redirect('staff_signup')
    
class StudentLoginView(View):
    def get(self, request, *args, **kwargs):
        form = AuthenticationForm()  # Login form
        return render(request, 'login.html', {'form': form, 'error_message': None})

    def post(self, request, *args, **kwargs):
        form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                return redirect('student_profile_logs')  # Redirect to the student_profile_logs page after successful login

        # If authentication fails, re-render the form with an error message
        return render(request, 'login.html', {
            'form': form,
            'error_message': 'Invalid username or password'
        })
        
def logout_view(request):
    logout(request)
    return redirect('login') 
        
@login_required
def profile_view(request):
    # The user is automatically available through the request object
    return render(request, 'profile.html', {'user': request.user})

class PlacementProfileView(View):
    def get(self, request):
        return render(request, 'placement_profile_form.html')

    def post(self, request):
        print("POST Data:", request.POST)
        print("FILES Data:", request.FILES)
        
        college_email = request.POST.get('college_email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        address_updated = request.POST.get('address_updated') == 'Yes' 
        experience_level = request.POST.get('experience_level')
        shift_requested = request.POST.get('shift_requested')
        preferred_facility_name = request.POST.get('preferred_facility_name')
        preferred_facility_address = request.POST.get('preferred_facility_address')
        preferred_facility_contact_person = request.POST.get('preferred_facility_contact_person')

        email_validator = EmailValidator()
        try:
            email_validator(college_email)
            if not college_email.endswith('@peakcollege.ca'):
                raise ValidationError('Must use @peakcollege.ca email')
        except ValidationError as e:
            print(f"Email validation failed: {e}")
            return render(request, 'placement_profile_form.html', {'error': str(e)})

        try:
            profile = PlacementProfile(
                user=request.user,
                college_email=college_email,
                first_name=first_name,
                last_name=last_name,
                address_updated=address_updated,
                experience_level=experience_level,
                shift_requested=shift_requested,
                preferred_facility_name=preferred_facility_name,
                preferred_facility_address=preferred_facility_address,
                preferred_facility_contact_person=preferred_facility_contact_person,
            )
            profile.save()
            print("PlacementProfile saved:", profile)
        except Exception as e:
            print(f"Error saving PlacementProfile: {e}")
            return render(request, 'placement_profile_form.html', {'error': 'Failed to save placement profile'})

        documents_data = [
            ('medical_certificate', 'Medical Certificate'),
            ('covid_vaccination_certificate', 'Covid Vaccination Certificate'),
            ('vulnerable_sector_check', 'Vulnerable Sector Check'),
            ('cpr_or_first_aid', 'CPR or First Aid'),
            ('mask_fit_certificate', 'Mask Fit Certificate'),
            ('bls_certificate', 'Basic Life Support'),
        ]

        for file_field, doc_type in documents_data:
            file = request.FILES.get(file_field)
            if file:
                try:
                    document = Document(profile=profile, document_type=doc_type, file=file)
                    document.save()
                    print(f"Document saved: {doc_type} - {file.name}")
                except Exception as e:
                    print(f"Error saving document {doc_type}: {e}")

        try:
            send_mail(
                'Placement Profile: Documents Under Review',
                'Your placement profile has been submitted successfully. Documents are under review.',
                settings.DEFAULT_FROM_EMAIL,
                [profile.college_email],
            )
            print(f"Email sent to {profile.college_email}")
        except Exception as e:
            print(f"Error sending email: {e}")

        return redirect('profile_submission_success')
    
class StudentProfileLogsView(View):
    def get(self, request):
        # Fetch the profile along with related documents in one query
        profile = PlacementProfile.objects.filter(user=request.user).prefetch_related('documents').first()
        
        # Prepare a combined structure for frontend (profile + document details)
        if profile:
            profile_details = {
                'first_name': profile.first_name,
                'last_name': profile.last_name,
                'college_email': profile.college_email,
                'experience_level': profile.experience_level,
                'shift_requested': profile.shift_requested,
                'address_updated': profile.address_updated,
                'preferred_facility_name': profile.preferred_facility_name,
                'preferred_facility_address': profile.preferred_facility_address,
                'preferred_facility_contact_person': profile.preferred_facility_contact_person,
                'documents': [
                    {
                        'document_type': document.document_type,
                        'file': document.file.url,  # Use the file URL to make it accessible on the frontend
                        'status': document.status,
                        'rejection_reason': document.rejection_reason,
                        'uploaded_at': document.uploaded_at
                    }
                    for document in profile.documents.all()
                ]
            }
        else:
            profile_details = None

        # Pass the profile details to the template
        return render(request, 'student_profile_logs.html', {
            'profile_details': profile_details
        })

def profile_submission_success(request):
    return render(request, 'profile_submission_success.html')

class DocumentView(View):
    def get(self, request, profile_id):
        form = DocumentForm()
        profile = PlacementProfile.objects.get(id=profile_id)
        return render(request, 'document_form.html', {'form': form, 'profile': profile})

    def post(self, request, profile_id):
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.profile = PlacementProfile.objects.get(id=profile_id)
            document.save()
            return JsonResponse({'message': 'Document uploaded successfully!'})
        return JsonResponse({'errors': form.errors}, status=400)


class ApproverView(View):
    def get(self, request):
        approvers = Approver.objects.all()
        return render(request, 'approvers_list.html', {'approvers': approvers})


class ApprovalLogView(View):
    def get(self, request):
        logs = ApprovalLog.objects.all()
        return render(request, 'approval_logs_list.html', {'logs': logs})


class FeeStatusView(View):
    def get(self, request):
        fee_statuses = FeeStatus.objects.all()
        return render(request, 'fee_status_list.html', {'fee_statuses': fee_statuses})


class PlacementNotificationView(View):
    def get(self, request):
        notifications = PlacementNotification.objects.all()
        return render(request, 'notifications_list.html', {'notifications': notifications})
