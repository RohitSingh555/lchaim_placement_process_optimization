import json
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import EmailMessage, send_mail
from django.core.validators import EmailValidator
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from private_healthcare_placement_optimization.enums import DocumentStatus
from .forms import CustomUserCreationForm, DocumentForm
from .models import (
    Approver,
    ApprovalLog,
    Document,
    FeeStatus,
    PlacementNotification,
    PlacementProfile,
)


def staff_required(view_func):
    return user_passes_test(lambda u: u.is_staff)(view_func)

@staff_required
def staff_only_view(request):
    return render(request, 'staff_page.html')

def signup(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()  # Save the user but do not log them in
            messages.success(request, "Account created successfully! Please log in.")
            return redirect('login')  # Redirect to login page
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CustomUserCreationForm()

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
        email = request.POST.get('username')  # Using 'username' since Django's default AuthenticationForm expects it
        password = request.POST.get('password')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            user = None

        if user is not None:
            authenticated_user = authenticate(request, username=user.username, password=password)

            if authenticated_user:
                login(request, authenticated_user)
                return redirect('student_profile_logs')  
        form = AuthenticationForm(request, data=request.POST)
        return render(request, 'login.html', {
            'form': form,
            'error_message': 'Invalid college email or password'
        })
        


def password_reset_request(request):
    """Handles password reset form submission"""
    if request.method == "POST":
        email = request.POST.get("email")
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, "Email address not found.")
            return redirect("password_reset")

        # Generate password reset link
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        reset_link = request.build_absolute_uri(f"/reset/{uid}/{token}/")

        # Send email
        email_subject = "Password Reset Request"
        email_body = render_to_string("password_reset_email.html", {"reset_link": reset_link, "user": user})
        send_mail(email_subject, email_body, settings.DEFAULT_FROM_EMAIL, [email])

        messages.success(request, "Password reset link sent to your email.")
        return redirect("password_reset_done")

    return render(request, "password_reset_form.html")


def password_reset_confirm(request, uidb64, token):
    """Handles setting a new password"""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError):
        messages.error(request, "Invalid password reset link.")
        return redirect("login")

    if request.method == "POST":
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect(request.path)

        user.set_password(password)
        user.save()
        messages.success(request, "Password reset successfully. You can now log in.")
        return redirect("login")

    return render(request, "password_reset_confirm.html")


def password_reset_complete(request):
    """Displays a success message after password reset"""
    return render(request, "password_reset_complete.html")        

        
def logout_view(request):
    logout(request)
    return redirect('login') 
        
@login_required
def profile_view(request):
    return render(request, 'profile.html', {'user': request.user})


class PlacementProfileView(View):
    def get(self, request):
        user = request.user
        return render(request, 'placement_profile_form.html', {
            'user': user,
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'college_email': user.email or ''
        })

    def post(self, request):
        print("POST Data:", request.POST)
        print("FILES Data:", request.FILES)

        user = request.user
        college_email = user.email 
        first_name = user.first_name
        last_name = user.last_name
        apt_house_no = request.POST.get('apt_house_no')
        street = request.POST.get('street')
        city = request.POST.get('city')
        province = request.POST.get('province')
        postal_code = request.POST.get('postal_code')
        open_to_outside_city = request.POST.get('open_to_outside_city') == 'Yes'
        experience_level = request.POST.get('experience_level')
        shift_requested = request.POST.get('shift_requested')
        preferred_facility_name = request.POST.get('preferred_facility_name')
        preferred_facility_address = request.POST.get('preferred_facility_address')
        preferred_facility_contact_person = request.POST.get('preferred_facility_contact_person')

        try:
            profile = PlacementProfile.objects.create(
                user=user,
                college_email=college_email,
                first_name=first_name,
                last_name=last_name,
                apt_house_no=apt_house_no,
                street=street,
                city=city,
                province=province,
                postal_code=postal_code,
                open_to_outside_city=open_to_outside_city,
                experience_level=experience_level,
                shift_requested=shift_requested,
                preferred_facility_name=preferred_facility_name,
                preferred_facility_address=preferred_facility_address,
                preferred_facility_contact_person=preferred_facility_contact_person,
            )
            print("PlacementProfile saved:", profile)
        except Exception as e:
            print(f"Error saving PlacementProfile: {e}")
            return render(request, 'placement_profile_form.html', {'error': 'Failed to save placement profile'})

        # Define required and optional documents
        documents_data = {
            'medical_certificate': 'Medical Certificate',
            'covid_vaccination_certificate': 'Covid Vaccination Certificate',
            'vulnerable_sector_check': 'Vulnerable Sector Check',
            'cpr_or_first_aid': 'CPR or First Aid',
            'mask_fit_certificate': 'Mask Fit Certificate',
            'bls_certificate': 'Basic Life Support',
            'experience_document': 'Experience Document'
        }

        missing_documents = []
        submitted_documents = []
        for file_field, doc_name in documents_data.items():
            file = request.FILES.get(file_field)

            if file:
                # Rename the file using "First Name, Last Name, Document Name"
                file_extension = file.name.split('.')[-1]
                new_file_name = f"{first_name}_{last_name}_{doc_name}.{file_extension}"

                # Save the file manually with the new filename
                file_path = os.path.join("documents/uploads", new_file_name)
                saved_path = default_storage.save(file_path, ContentFile(file.read()))

                submitted_documents.append(doc_name)
            else:
                missing_documents.append(doc_name)
                saved_path = None  # No file uploaded

            try:
                document_entry = Document.objects.create(
                    profile=profile,
                    document_type=doc_name,
                    file=saved_path if saved_path else None,  # Save file path
                    file_name=new_file_name if file else None
                )

                if file:
                    print(f"Document saved: {doc_name} - {new_file_name}")
                else:
                    print(f"Document entry created for missing: {doc_name}")

            except Exception as e:
                print(f"Error saving document {doc_name}: {e}")

        # Check for missing required documents
        required_document_keys = {'medical_certificate', 'covid_vaccination_certificate', 
                                  'vulnerable_sector_check', 'cpr_or_first_aid', 
                                  'mask_fit_certificate', 'bls_certificate'}
        
        missing_required_docs = [documents_data[key] for key in required_document_keys if key in missing_documents]

        # Send appropriate email based on document submission status
        if not missing_required_docs:
            try:
                send_welcome_email(profile, submitted_documents)
                print(f"Welcome email sent to {profile.college_email}")
            except Exception as e:
                print(f"Error sending welcome email: {e}")
        else:
            try:
                send_documents_incomplete_email(profile, missing_required_docs)
                print(f"Documents incomplete email sent to {profile.college_email}")
            except Exception as e:
                print(f"Error sending incomplete documents email: {e}")

        return redirect('student_profile_logs')
    
    
def send_documents_incomplete_email(profile, missing_documents):
    """Send an email notifying the student about missing documents dynamically."""
    subject = "Placement Profile: Documents Incomplete"

    remaining_documents_html = "".join([f"<li>{doc}</li>" for doc in missing_documents])

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
            .highlight {{
                color: #008080;
            }}
            img {{
                width: 250px;
                height: 120px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Placement Profile: Documents Incomplete</h2>
            <p>Greetings!</p>
            <p>Thank you for creating your profile.</p>
            <p>To submit the remaining requirements, please log in to your profile again and complete the submission process.</p>
            <p>The placement coordinators will begin reviewing your documents only once all requirements are submitted and your balance is cleared.</p>
            <p><b>Remaining documents to submit:</b></p>
            <ul>
                {remaining_documents_html}
            </ul>
            <p><a href="https://www.peakcollege.ca/student-view" class="highlight">Placement Link: Click here.</a></p>
            <p>Best of luck with your placement process and thanks again for completing your Placement Profile at Peak College!</p>
            <div class="footer">
                <p>Warm regards, <br> The Peak Healthcare Team</p>
                <p>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></p>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
                <p>1140 Sheppard Ave West - Unit #12, North York, ON, M3K 2A2</p>
            </div>
        </div>
    </body>
    </html>
    """

    try:
        send_mail(
            subject,
            "",  # Empty text version
            settings.DEFAULT_FROM_EMAIL,
            [profile.college_email],
            html_message=message,
        )
        print(f"Documents incomplete email sent to {profile.college_email}")
    except Exception as e:
        print(f"Error sending email: {e}")
    
def send_welcome_email(profile, submitted_documents):
    """Send a welcome email when a student's documents are under review."""
    subject = "Placement Profile: Documents Under Review"
    
    document_list_html = "".join(f"<li>{doc}</li>" for doc in submitted_documents)
    
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
            img {{
                width: 250px;
                height: 120px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Placement Profile: Documents Under Review</h2>
            <p>Greetings!</p>
            <p>Your documents are now <span class="bold">UNDER REVIEW</span> by our team.</p>
            <p>The following documents have been submitted:</p>
            <ul>
                {document_list_html}
            </ul>
            <p>Next step: wait for the approval of your submitted documents. You’ll receive another email once all are approved.</p>
            <p>Best of luck with your placement process and thanks again for completing your Placement Profile at Peak College!</p>
            <div class="footer">
                <p>Warm regards, <br> The Peak Healthcare Team</p>
                <p>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></p>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
                <p>1140 Sheppard Ave West - Unit #12, North York, ON, M3K 2A2</p>
            </div>
        </div>
    </body>
    </html>
    """

    try:
        send_mail(
            subject,
            "",  # Empty text version
            settings.DEFAULT_FROM_EMAIL,
            [profile.college_email],
            html_message=message,
        )
        print(f"Email sent to {profile.college_email}")
    except Exception as e:
        print(f"Error sending email: {e}")
    

class SendDocumentsEmailView(View):
    def post(self, request, *args, **kwargs):
        profile_id = request.POST.get("profile_id")
        profile = get_object_or_404(PlacementProfile, id=profile_id)
        documents = Document.objects.filter(profile=profile, file__isnull=False)

        valid_documents = []
        for document in documents:
            if document.file and document.file.name:  # Ensure the file exists
                try:
                    file_path = document.file.path
                    valid_documents.append((file_path, os.path.basename(file_path)))
                except ValueError:
                    continue  # Skip documents without a valid file path

        if not valid_documents:
            return JsonResponse({"error": "No valid documents available for this profile"}, status=400)

        # Generate document list for email
        document_list_html = "".join([f"<li>{file_name}</li>" for _, file_name in valid_documents])

        # Email Content with HTML Formatting
        email_subject = f"Submitted Documents for {profile.first_name} {profile.last_name}"
        email_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background-color: #f9f9f9;
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #ffffff;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                }}
                h2 {{
                    color: #2c3e50;
                }}
                p {{
                    margin: 10px 0;
                }}
                .document-list {{
                    background: #f3f3f3;
                    padding: 10px;
                    border-radius: 5px;
                    list-style-type: none;
                }}
                .document-list li {{
                    padding: 5px;
                }}
                .footer {{
                    margin-top: 20px;
                    font-size: 12px;
                    color: #555;
                }}
                .highlight {{
                    font-weight: bold;
                    color: #2c3e50;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Dear Documents Team,</h2>
                <p>Please find attached the submitted documents for <span class="highlight">{profile.first_name} {profile.last_name}</span>.</p>
                
                <h3>List of Documents:</h3>
                <ul class="document-list">
                    {document_list_html}
                </ul>

                <p>If you have any questions or require further information, feel free to reach out.</p>
                
                <p class="footer">Best Regards, <br><strong>Peak College Admissions Team</strong></p>
            </div>
        </body>
        </html>
        """

        email = EmailMessage(
            subject=email_subject,
            body=email_body,
            from_email="no-reply@peakcollege.ca",
            to=["documents@peakcollege.ca"],
        )
        email.content_subtype = "html" 

        # Attach each document
        for file_path, file_name in valid_documents:
            try:
                with open(file_path, "rb") as file:
                    email.attach(file_name, file.read(), "application/octet-stream")
            except Exception as e:
                return JsonResponse({"error": f"Error attaching file {file_name}: {str(e)}"}, status=500)

        # Send Email
        try:
            email.send()
            return JsonResponse({"message": "Email sent successfully"})
        except Exception as e:
            return JsonResponse({"error": f"Failed to send email: {str(e)}"}, status=500)
    
class StudentProfileLogsView(View):
    def get(self, request):
        # Check if user is authenticated
        if not request.user.is_authenticated:
            return redirect('/login/')  # Redirect if not logged in

        is_approver = Approver.objects.filter(user=request.user).exists()
        is_superuser = request.user.is_superuser  # Check if user is superuser

        if is_approver:
            profiles = PlacementProfile.objects.prefetch_related('documents').all()
        else:
            profiles = PlacementProfile.objects.filter(user=request.user).prefetch_related('documents')

        profile_details = []
        for profile in profiles:
            document_details = []
            for document in profile.documents.all():
                approval_logs = ApprovalLog.objects.filter(document=document)
                approver_actions = [
                    {
                        "approver": log.approver.full_name if log.approver else "Unknown",
                        "action": log.action,
                        "reason": log.reason,
                        "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    for log in approval_logs
                ]
                
                document_details.append({
                    'id': document.id,
                    'status': document.status,
                    'document_type': document.document_type,
                    'file': document.file.url if document.file else None,
                    'rejection_reason': document.rejection_reason,
                    'uploaded_at': document.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                    'approval_logs': approver_actions
                })
            
            profile_details.append({
                'profile_id': profile.id,
                'first_name': profile.first_name,
                'last_name': profile.last_name,
                'college_email': profile.college_email,
                'experience_level': profile.experience_level,
                'shift_requested': profile.shift_requested,
                'preferred_facility_name': profile.preferred_facility_name,
                'preferred_facility_address': profile.preferred_facility_address,
                'preferred_facility_contact_person': profile.preferred_facility_contact_person,
                'documents': document_details
            })

        return render(request, 'student_profile_logs.html', {
            'profile_details': profile_details,
            'is_approver': is_approver,
            'is_superuser': is_superuser  # Pass to the template
        })


@user_passes_test(lambda u: u.is_superuser)  # Only allow superusers
def delete_profile(request, profile_id):
    profile = get_object_or_404(PlacementProfile, id=profile_id)
    profile.delete()
    return JsonResponse({'message': 'Profile deleted successfully!'})

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
                max-width: 100%;
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
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
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

def send_email_notify_result(profile, rejected_documents):
    subject = 'Placement Profile: Resubmit Rejected Documents'
    
    # Build the dynamic list of rejected documents
    document_list_html = ""
    for doc in rejected_documents:
        reason = doc.rejection_reason if doc.rejection_reason else "No reason provided"
        document_list_html += f"<li><span class='bold'>{doc.document_type}:</span> {reason}</li>"

    # Updated message with dynamic document list
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
            img{{
            width: 250px;
            height: 120px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Placement Profile: Resubmit Rejected Documents</h2>
            <p>Greetings!</p>
            <p>The documents below were rejected due to the following reasons:</p>
            <ul>
                {document_list_html}
            </ul>
            <p>Next step: address the reasons and resubmit the documents by clicking the link below.</p>
            <p><a href="https://www.peakcollege.ca/student-view" class="highlight">Resubmission Link: Click here!</a></p>
            <p>You’ll receive another email once all are approved.</p>
            <div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement Profile at Peak College!</p>
                <p>Warm regards, <br> The Peak Healthcare Team</p>
                <p>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></p>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
                <p>1140 Sheppard Ave West - Unit #12, North York, ON, M3K 2A2</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Send the email
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [profile.college_email],
        html_message=message
    )

def send_email_done(profile, documents):
    subject = f'{profile.first_name} {profile.last_name} - Placement Profile: Documents Approved'
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
                max-width: 100%;
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
            <h2>{profile.first_name} is now ready for placement.</h2>
            <p>Greetings!</p>
            <p>All your documents are now <span class="highlight">APPROVED</span>.</p>
            <p>The Placement Coordinator: We will reach out to you through email or phone call. Once you finalize with her which facility you’re going to do your placement, she will inform you of your Placement Orientation Date.</p>
            <p>Then you can pick up your Skills Passbook and NACC Reviewer from the school on any operating day.</p>
            <h4>School Office Hours:</h4>
            <p><span class="bold">Monday to Thursday:</span> 9:30 AM to 5:00 PM</p>
            <p><span class="bold">Saturday:</span> 9:30 AM to 4:00 PM</p>
            <div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement Profile at Peak College!</p>
                <p>Warm regards, <br> The Peak Healthcare Team</p>
                <p>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></p>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
                <p>1140 Sheppard Ave West - Unit #12, North York, ON, M3K 2A2</p>
            </div>
        </div>
    </body>
    </html>
    """

    email = EmailMessage(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [profile.college_email]
    )
    email.content_subtype = "html" 

    for document in documents:
        if document.file: 
            email.attach(document.file.name, document.file.read())

    email.send()

def send_placement_email(profile):
    subject = f'{profile.first_name} {profile.last_name} - Placement Profile Completed'
    message = f'''
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; background-color: #f9f9f9; padding: 20px; }}
            .container {{ background-color: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); }}
            h2 {{ color: #008080; }}
            p {{ font-size: 16px; line-height: 1.5; }}
            .footer {{ margin-top: 20px; font-size: 14px; color: #555; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Placement Profile Completed</h2>
            <h2>{profile.first_name} {profile.last_name} is now ready for placement.</h2>
            <p>Dear Placement Team,</p>
            <p>This is to inform you that <strong>{profile.first_name} {profile.last_name}</strong> has successfully completed their placement profile.</p>
            <p>All required documents have been submitted and approved. Please proceed with the necessary steps to coordinate their placement at an appropriate facility.</p>
            <p>If any additional information is needed, feel free to reach out.</p>
            <div class="footer">
                <p>Best regards,</p>
                <p><strong>[Your Name]</strong><br>
                Peak College Placement Coordinator<br>
                <a href="mailto:placement@peakcollege.ca">placement@peakcollege.ca</a></p>
            </div>
        </div>
    </body>
    </html>
'''
    
    email = EmailMessage(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        ["placement@peakcollege.ca"]
    )
    email.content_subtype = "html" 
    email.send()

def send_documents_email(profile, documents):
    subject = f'{profile.first_name} {profile.last_name} - Documents Completed'
    message = f'''
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; background-color: #f9f9f9; padding: 20px; }}
            .container {{ background-color: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); }}
            h2 {{ color: #008080; }}
            p {{ font-size: 16px; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Documents Completed</h2>
            <h2>{profile.first_name}'s Complete Files for Placement</h2>
            <p>Greetings!</p>
            <p>Student's all necessary documents have been completed for placement. Please find the attached documents.</p>
            <p>Thank you!</p>
        </div>
    </body>
    </html>
    '''
    
    email = EmailMessage(
        subject=subject,
        body=message,
        from_email="no-reply@peakcollege.ca",
        to=["documents@peakcollege.ca"],
    )
    email.content_subtype = "html"

    valid_documents = []
    for document in documents:
        if document.file and document.file.name:
            try:
                file_path = document.file.path
                valid_documents.append((file_path, os.path.basename(file_path)))
            except ValueError:
                continue  # Skip documents without a valid file path

    # Attach each document
    for file_path, file_name in valid_documents:
        try:
            with open(file_path, "rb") as file:
                email.attach(file_name, file.read(), "application/octet-stream")
        except Exception as e:
            print(f"Error attaching file {file_name}: {str(e)}")

    try:
        email.send()
        return {"message": "Email sent successfully"}
    except Exception as e:
        return {"error": f"Failed to send email: {str(e)}"}
    

def send_email_resubmit(profile, documents):
    # Fetch all approvers (linked to User model)
    approvers = Approver.objects.select_related('user').all()

    # Collect all approver email addresses
    approver_emails = [approver.user.email for approver in approvers]

    subject = f"Corrected File Submitted by {profile.first_name} {profile.last_name}"
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
                max-width: 100%;
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
            <h2>Corrected File Submitted</h2>
            <p>Greetings!</p>
            <p>The student <span class="bold">{profile.first_name} {profile.last_name}</span> has resubmitted the corrected documents for your review.</p>
            <p>Click the link below to assess (approve or reject) the submission:</p>
            <p><a href="https://www.peakcollege.ca/approver-view" class="highlight">Approver's View: Click here to log in!</a></p>
            <p>Please review and take the necessary action.</p>
            <div class="footer">
                <p>Warm regards, <br> The Peak Healthcare Team</p>
                <p>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></p>
                <p>1140 Sheppard Ave West - Unit #12, North York, ON, M3K 2A2</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Send email to all approvers
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        approver_emails,
        html_message=message
    )


def handle_button_action(request, profile_id, action):
    try:
        profile = PlacementProfile.objects.prefetch_related("documents").get(id=profile_id)

        documents = profile.documents.all()

        if action == 'remind_fee':
            send_email_remind_fee(profile)
        elif action == 'notify_result':
            rejected_documents = documents.filter(status="Rejected")
            send_email_notify_result(profile, rejected_documents)
        elif action == 'done':
            send_email_done(profile, documents)
            send_placement_email(profile)
            send_documents_email(profile, documents)
        elif action == 'resubmit':
            send_email_resubmit(profile, documents)

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
    
def superuser_required(user):
    return user.is_superuser

@user_passes_test(superuser_required, login_url='/404/')
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
        
def submit_new_file(request):
    if request.method == "POST":
        document_id = request.POST.get("document_id")
        new_file = request.FILES.get("file")

        if not document_id or not new_file:
            return JsonResponse({"success": False, "error": "Missing document ID or file."})

        existing_document = get_object_or_404(Document, id=document_id)
        profile = existing_document.profile
        document_type = existing_document.document_type
        file_extension = new_file.name.split('.')[-1]
        new_file_name = f"{profile.first_name}_{profile.last_name}_{document_type}.{file_extension}"
        file_path = os.path.join("documents/uploads", new_file_name)

        saved_path = default_storage.save(file_path, ContentFile(new_file.read()))
        
        new_document = Document.objects.create(
            profile=profile,
            document_type=document_type,
            file=saved_path,
            file_name=new_file_name,
            status="In Review"
        )
        
        existing_document.delete()

        return JsonResponse({"success": True, "new_document_id": new_document.id})
    
    return JsonResponse({"success": False, "error": "Invalid request method."})


@csrf_exempt  # Optional: For local testing. Remove or replace with CSRF handling in production.
@login_required  # Ensure only authenticated users can access this endpoint
def validate_password(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            entered_password = data.get("password")

            # Get the currently logged-in user
            user = get_user(request)

            # Validate the password
            if user.check_password(entered_password):
                return JsonResponse({"valid": True})
            else:
                return JsonResponse({"valid": False})
        except (json.JSONDecodeError, KeyError):
            return JsonResponse({"error": "Invalid request data"}, status=400)
    else:
        return JsonResponse({"error": "Invalid method"}, status=405)
    

def custom_login_required(function=None, login_url=None):
    actual_decorator = user_passes_test(
        lambda u: u.is_authenticated,
        login_url=reverse("custom_404"),
    )
    if function:
        return actual_decorator(function)
    return actual_decorator

def custom_404(request, exception=None):
    return render(request, "404.html", status=404)

@login_required
def profile_view(request):
    return render(request, 'profile.html', {'user': request.user})