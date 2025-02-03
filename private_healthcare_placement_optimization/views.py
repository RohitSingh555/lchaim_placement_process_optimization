from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from private_healthcare_placement_optimization.enums import DocumentStatus
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
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User

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
        if request.session.get('password_verified', False):
            form = UserCreationForm()
            return render(request, 'staff_signup.html', {'form': form, 'password_verified': True})

        return render(request, 'staff_signup.html', {'password_verified': False})

    def post(self, request, *args, **kwargs):
        if 'password' in request.POST:
            access_password = request.POST.get('password')
            if access_password == '1234':
                request.session['password_verified'] = True
                return redirect('staff_signup')
            else:
                return render(request, 'staff_signup.html', {
                    'password_verified': False,
                    'error_message': 'Incorrect password.'
                })

        if request.session.get('password_verified', False):
            form = UserCreationForm(request.POST)
            if form.is_valid():
                user = form.save()
                user.is_staff = True
                user.save()

                Approver.objects.create(
                    user=user,
                    full_name=f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else user.username,
                    position="Staff"  
                )

                return redirect('login')

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

        return redirect('student_profile_logs')
    

from django.contrib.auth.mixins import LoginRequiredMixin
class StudentProfileLogsView(LoginRequiredMixin, View):
    login_url = '/login/'

    def get(self, request):
        is_approver = Approver.objects.filter(user=request.user).exists()

        if is_approver:
            profiles = PlacementProfile.objects.prefetch_related('documents').all()
        else:
            profiles = PlacementProfile.objects.filter(user=request.user).prefetch_related('documents')

        profile_details = [
            {
                'profile_id': profile.id,
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
                        'id': document.id,
                        'status': document.status,
                        'document_type': document.document_type,
                        'file': document.file,  
                        'rejection_reason': document.rejection_reason,
                        'uploaded_at': document.uploaded_at
                    }
                    for document in profile.documents.all()
                ]
            }
            for profile in profiles
        ]

        return render(request, 'student_profile_logs.html', {
            'profile_details': profile_details
        })


@csrf_exempt
@login_required
def approve_document(request, document_id):
    if request.method == "POST":
        document = get_object_or_404(Document, id=document_id)
        approver = get_object_or_404(Approver, user=request.user)

        action = request.POST.get("action")  
        rejection_reason = request.POST.get("reason", "").strip()

        valid_actions = {DocumentStatus.APPROVED.value, DocumentStatus.REJECTED.value, DocumentStatus.IN_REVIEW.value}
        if action not in valid_actions:
            return JsonResponse({"error": "Invalid action"}, status=400)

        document.status = action
        document.rejection_reason = rejection_reason if action == DocumentStatus.REJECTED.value else None
        document.save()

        ApprovalLog.objects.create(
            approver=approver,
            document=document,
            action=action,
            reason=rejection_reason if action == DocumentStatus.REJECTED.value else None,
        )

        # Send placement notification
        message = f"Your document '{document.document_type}' has been {action.lower()}."
        if action == DocumentStatus.REJECTED.value:
            message += f" Reason: {rejection_reason}"

        PlacementNotification.objects.create(
            profile=document.profile,
            subject=f"Document {action}: {document.document_type}",
            message=message
        )

        # Return updated document details
        return JsonResponse({
            "message": f"Document {action.lower()} successfully!",
            "document": {
                "id": document.id,
                "document_type": document.document_type,
                "status": document.status,
                "rejection_reason": document.rejection_reason,
                "uploaded_at": document.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                "file": document.file.url if document.file else None,
            }
        }, status=200)

    return JsonResponse({"error": "Invalid request"}, status=400)

def send_email_remind_fee(profile):
    subject = 'Placement Profile: Settle Tuition Fee Balance'
    message = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: linear-gradient(to bottom, rgba(0, 128, 128, 0.1), #ffffff);
                padding: 20px;
                color: #333;
            }}
            .container {{
                background-color: #ffffff;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                width: 100%;
                max-width: 600px;
                margin: auto;
            }}
            h2 {{
                color: #008080;
                font-size: 24px;
            }}
            p {{
                line-height: 1.6;
                font-size: 16px;
            }}
            .footer {{
                margin-top: 20px;
                font-size: 14px;
                color: #555;
            }}
            .footer a {{
                color: #008080;
                text-decoration: none;
            }}
            .bold {{
                font-weight: bold;
            }}
            .highlight {{
                color: #008080;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Placement Profile: Settle Tuition Fee Balance</h2>
            <p>Greetings!</p>
            <p>Thank you for creating your Placement Profile! You still have an outstanding balance. Please pay your tuition fee to avoid any delays in the process. This will help us move forward smoothly with your placement.</p>
            <h3>Payment Options:</h3>
            <ul>
                <li>E-Transfer to: <span class="highlight">payment@peakcollege.ca</span></li>
                <li>Cash, Credit, or Debit Payment on Campus</li>
            </ul>
            <h4>School Office Hours:</h4>
            <p><span class="bold">Monday to Thursday:</span> 9:30 AM to 5:00 PM</p>
            <p><span class="bold">Saturday:</span> 9:30 AM to 4:00 PM</p>
            <div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement Profile at Peak College!</p>
                <p>Warm regards, <br> The Peak Healthcare Team</p>
                <p>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></p>
                <p>1140 Sheppard Ave West - Unit #12, North York, ON, M3K 2A2</p>
            </div>
        </div>
    </body>
    </html>
    """
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [profile.college_email],
        html_message=message
    )

def send_email_notify_result(profile):
    subject = 'Placement Profile: Resubmit Rejected Documents'
    message = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: linear-gradient(to bottom, rgba(0, 128, 128, 0.1), #ffffff);
                padding: 20px;
                color: #333;
            }}
            .container {{
                background-color: #ffffff;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                width: 100%;
                max-width: 600px;
                margin: auto;
            }}
            h2 {{
                color: #008080;
                font-size: 24px;
            }}
            p {{
                line-height: 1.6;
                font-size: 16px;
            }}
            .footer {{
                margin-top: 20px;
                font-size: 14px;
                color: #555;
            }}
            .footer a {{
                color: #008080;
                text-decoration: none;
            }}
            .bold {{
                font-weight: bold;
            }}
            .highlight {{
                color: #008080;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Placement Profile: Resubmit Rejected Documents</h2>
            <p>Greetings!</p>
            <p>The documents below were rejected due to the following reasons:</p>
            <ul>
                <li><span class="bold">Letter from Employer:</span> Unclear content</li>
                <li><span class="bold">Vulnerable Sector Check:</span> Expired Document</li>
            </ul>
            <p>Next step: address the reasons and resubmit the documents by clicking the link below.</p>
            <p><a href="https://www.peakcollege.ca/student-view" class="highlight">Resubmission Link: Click here!</a></p>
            <p>You’ll receive another email once all are approved.</p>
            <div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement Profile at Peak College!</p>
                <p>Warm regards, <br> The Peak Healthcare Team</p>
                <p>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></p>
                <p>1140 Sheppard Ave West - Unit #12, North York, ON, M3K 2A2</p>
            </div>
        </div>
    </body>
    </html>
    """
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [profile.college_email],
        html_message=message
    )

def send_email_done(profile):
    subject = 'Placement Profile: Documents Approved'
    message = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: linear-gradient(to bottom, rgba(0, 128, 128, 0.1), #ffffff);
                padding: 20px;
                color: #333;
            }}
            .container {{
                background-color: #ffffff;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                width: 100%;
                max-width: 600px;
                margin: auto;
            }}
            h2 {{
                color: #008080;
                font-size: 24px;
            }}
            p {{
                line-height: 1.6;
                font-size: 16px;
            }}
            .footer {{
                margin-top: 20px;
                font-size: 14px;
                color: #555;
            }}
            .footer a {{
                color: #008080;
                text-decoration: none;
            }}
            .bold {{
                font-weight: bold;
            }}
            .highlight {{
                color: #008080;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Placement Profile: Documents Approved</h2>
            <p>Greetings!</p>
            <p>All your documents are now <span class="highlight">APPROVED</span>.</p>
            <p>The Placement Coordinator: Grace Doton will reach out to you through email or phone call. Once you finalize with her which facility you’re going to do your placement, she will inform you of your Placement Orientation Date.</p>
            <p>Then you can pick up your Skills Passbook and NACC Reviewer from the school on any operating day.</p>
            <h4>School Office Hours:</h4>
            <p><span class="bold">Monday to Thursday:</span> 9:30 AM to 5:00 PM</p>
            <p><span class="bold">Saturday:</span> 9:30 AM to 4:00 PM</p>
            <div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement Profile at Peak College!</p>
                <p>Warm regards, <br> The Peak Healthcare Team</p>
                <p>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></p>
                <p>1140 Sheppard Ave West - Unit #12, North York, ON, M3K 2A2</p>
            </div>
        </div>
    </body>
    </html>
    """
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [profile.college_email],
        html_message=message
    )


def handle_button_action(request, profile_id, action):
    try:
        profile = PlacementProfile.objects.get(id=profile_id)
        
        if action == 'remind_fee':
            send_email_remind_fee(profile)
        elif action == 'notify_result':
            send_email_notify_result(profile)
        elif action == 'done':
            send_email_done(profile)
        
        return JsonResponse({"status": "success", "message": f"Email sent for action {action}"})
    
    except PlacementProfile.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Profile not found"})

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
    
def approvers_view(request):
    approvers = User.objects.all()
    approvers_data = []

    for user in approvers:
        try:
            # Check if the user has an associated approver
            approver = user.approver_profile
            approvers_data.append({
                'user': user,
                'role': 'Approver',  # Display 'Approver' if the approver exists
                'full_name': approver.full_name,
                'position': approver.position,
            })
        except Approver.DoesNotExist:
            # If no approver exists, display 'Student'
            approvers_data.append({
                'user': user,
                'role': 'Student',  # Display 'Student' if no approver
                'full_name': user.username,  # Display username as full name
                'position': '',  # No position for student
            })

    return render(request, 'approvers_list.html', {'approvers': approvers_data})


def promote_to_approver(request, user_id):
    try:
        user = get_object_or_404(User, id=user_id)
        # Promote user to approver
        user.is_staff = True
        user.save()
        
        # Create approver entry
        Approver.objects.create(
            user=user,
            full_name=f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else user.username,
            position="Staff"
        )

        return JsonResponse({
            'status': 'success',
            'message': f'{user.username} has been promoted to approver.'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })

# Remove a user from approver
def remove_from_approver(request, user_id):
    try:
        user = get_object_or_404(User, id=user_id)
        
        # Remove approver entry
        approver = Approver.objects.filter(user=user).first()
        if approver:
            approver.delete()
        
        # Revert user's is_staff status
        user.is_staff = False
        user.save()

        return JsonResponse({
            'status': 'success',
            'message': f'{user.username} has been removed from approvers.'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })