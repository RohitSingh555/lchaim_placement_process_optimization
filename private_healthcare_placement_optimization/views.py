from datetime import datetime
import json
import os
import re

import zipfile
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.core.mail import EmailMessage
from django.views import View
from .models import PlacementProfile, Document
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views import View
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import EmailMessage, send_mail
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy

from private_healthcare_placement_optimization.enums import DocumentStatus
from .forms import CustomUserCreationForm, DocumentForm, FacilityForm, OrientationDateForm
from .models import (
    Approver,
    ApprovalLog,
    City,
    Document,
    Facility,
    OrientationDate,
    PlacementNotification,
    PlacementProfile,
    StudentID,
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
        city_preference_1 = request.POST.get('city_preference_1')
        city_preference_2 = request.POST.get('city_preference_2')
        gender = request.POST.get('gender')

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
                city_preference_1=city_preference_1,
                city_preference_2=city_preference_2,
                gender=gender,
            )
        except Exception as e:
            print(f"Error saving PlacementProfile: {e}")
            return render(request, 'placement_profile_form.html', {'error': 'Failed to save Placement'})

        documents_data = {
            'medical_certificate': 'Medical Certificate',
            'covid_vaccination_certificate': 'Covid Vaccination Certificate',
            'vulnerable_sector_check': 'Vulnerable Sector Check',
            'cpr_or_first_aid': 'CPR or First Aid',
            'mask_fit_certificate': 'Mask Fit Certificate',
            'bls_certificate': 'Basic Life Support',
            'experience_document': 'Experience Document',
            'resume': 'Resume',
            'skills_passbook': 'Skills Passbook',
            'x_ray_result': 'X-Ray Result',
            'mmr_lab_vax_record': 'MMR Lab/Vax Record',
            'varicella_lav_vax_record': 'Varicella Lab/Vax Record',
            'tdap_vax_record': 'TDAP Vax Record',
            'hepatitits_b_lab_vax_record': 'Hepatitis B Lab/Vax Record',
            'flu_shot': 'Flu Shot',
            'extra_dose_of_covid': 'Extra Dose of Covid',
            'other_documents': 'Other Documents',
        }

        missing_documents = []
        submitted_documents = []
        for file_field, doc_name in documents_data.items():
            file = request.FILES.get(file_field)

            if file:
                file_extension = file.name.split('.')[-1]
                new_file_name = f"{first_name}_{last_name}_{doc_name}.{file_extension}"

                file_path = os.path.join("documents/uploads", new_file_name)
                saved_path = default_storage.save(file_path, ContentFile(file.read()))

                submitted_documents.append(doc_name)
            else:
                missing_documents.append(file_field)
                saved_path = None 

            try:
                document_entry = Document.objects.create(
                    profile=profile,
                    document_type=doc_name,
                    file=saved_path if saved_path else None, 
                    file_name=new_file_name if file else None
                )

                if file:
                    print(f"Document saved: {doc_name} - {new_file_name}")
                else:
                    print(f"Document entry created for missing: {doc_name}")

            except Exception as e:
                print(f"Error saving document {doc_name}: {e}")

        required_document_keys = {'medical_certificate', 'covid_vaccination_certificate', 
                                  'vulnerable_sector_check', 'cpr_or_first_aid',
                                  'mask_fit_certificate', }
        
        missing_required_docs = [documents_data[key] for key in required_document_keys if key in missing_documents]

        if not missing_required_docs:
            try:                
                messages.error(
                    request, 
                    "Your documents are now <strong>UNDER REVIEW</strong> by our team.<br><br>Next step, wait for the approval of your submitted documents.<br><br>You’ll receive another email once all are approved."
                )
                send_welcome_email(profile, submitted_documents)
                print(f"Welcome email sent to {profile.college_email}")
            except Exception as e:
                print(f"Error sending welcome email: {e}")
        else:
            try: 
                messages.success(
                request,
                "Thank you for creating your profile.<br><br>"
                "To submit the remaining requirements, please log in to your profile again and complete the submission process.<br><br>"
                "The Placement Team will begin reviewing your documents only once all requirements are submitted and your balance is cleared."
            )
                send_documents_incomplete_email(profile, missing_required_docs)
                print(f"Documents incomplete email sent to {profile.college_email}")
            except Exception as e:
                print(f"Error sending incomplete documents email: {e}")

        return redirect('student_profile_logs')
    
    
def send_documents_incomplete_email(profile, missing_documents):
    """Send an email notifying the student about missing documents dynamically."""
    subject = "Placement: Documents Incomplete"

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
                width: 240px;
                height: 90px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <p>Greetings!</p>
            <p>Thank you for creating your profile.</p>
            <p>To submit the remaining requirements, please log in to your profile again and complete the submission process.</p>
            <p>The Placement Team will begin reviewing your documents only once all requirements are submitted and your balance is cleared.</p>
            <p><b>Remaining documents to submit:</b></p>
            <ul>
                {remaining_documents_html}
            </ul>
            <p><a href="https://www.peakcollege.ca" class="highlight">Placement Link: Click here.</a></p>
            <div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement at Peak College!</p>
                <span>Warm regards, </span>
                <br>
                <span> The Peak Healthcare Team</span>
                <br>
                <span>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></span>
                <br>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
                <br>
                <span>1140 Sheppard Ave West</span>
                <br>
                <span>Unit #12, North York, ON</span>
                <br>
                <span>M3K 2A2</span>
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
    subject = "Placement: Documents Under Review"
    
    
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
                width: 240px;
                height: 90px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <p>Greetings!</p>
            <p>Your documents are now <span class="bold">UNDER REVIEW</span> by our team.</p>
            <p>Next step, wait for the approval of your submitted documents. You’ll receive another email once all are approved.</p>
            <div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement at Peak College!</p>
                <span>Warm regards, </span>
                <br>
                <span> The Peak Healthcare Team</span>
                <br>
                <span>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></span>
                <br>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
                <br>
                <span>1140 Sheppard Ave West</span>
                <br>
                <span>Unit #12, North York, ON</span>
                <br>
                <span>M3K 2A2</span>
            </div>
        </div>
    </body>
    </html>
    """

    try:
        send_mail(
            subject,
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
            if document.file and document.file.name:
                try:
                    file_path = document.file.path
                    valid_documents.append((file_path, os.path.basename(file_path)))
                except ValueError:
                    continue

        if not valid_documents:
            return JsonResponse({"error": "No valid documents available for this profile"}, status=400)

        # Create ZIP file
        safe_first_name = re.sub(r'\W+', '_', profile.first_name.lower())
        safe_last_name = re.sub(r'\W+', '_', profile.last_name.lower())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        zip_filename = f"{profile.id:02d}_{safe_first_name}_{safe_last_name}_{timestamp}.zip"
        zip_dir = os.path.join(settings.MEDIA_ROOT, "zips")
        os.makedirs(zip_dir, exist_ok=True)
        zip_path = os.path.join(zip_dir, zip_filename)

        try:
            with zipfile.ZipFile(zip_path, "w") as zipf:
                for file_path, file_name in valid_documents:
                    zipf.write(file_path, arcname=file_name)
        except Exception as e:
            return JsonResponse({"error": f"Failed to create zip: {str(e)}"}, status=500)

        # Create download URL
        zip_url = request.build_absolute_uri(os.path.join(settings.MEDIA_URL, "zips", zip_filename))

        # Email Content
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
                h2 {{ color: #2c3e50; }}
                a.download-link {{
                    display: inline-block;
                    margin-top: 15px;
                    padding: 10px 15px;
                    background-color: #2c3e50;
                    color: white;
                    border-radius: 5px;
                    text-decoration: none;
                }}
                .footer {{
                    margin-top: 20px;
                    font-size: 12px;
                    color: #555;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Dear Documents Team,</h2>
                <p>Please find below a link to download the submitted documents for <strong>{profile.first_name} {profile.last_name}</strong>.</p>
                
                <a href="{zip_url}" class="download-link" target="_blank">Download Documents (ZIP)</a>

                <p>If you have any questions or require further information, feel free to reach out.</p>
                
                <div class="footer">
                    <p>Best of luck with your placement process and thanks again for completing your Placement at Peak College!</p>
                    <p>Warm regards,<br>The Peak Healthcare Team</p>
                    <p><a href="https://www.peakcollege.ca">www.peakcollege.ca</a></p>
                    <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg" width="240" height="90"/>
                    <p>1140 Sheppard Ave West, Unit #12, North York, ON M3K 2A2</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Send Email without attachments
        email = EmailMessage(
            subject=email_subject,
            body=email_body,
            from_email="no-reply@peakcollege.ca",
            to=["documents@peakcollege.ca"],
        )
        email.content_subtype = "html"

        try:
            email.send()
            return JsonResponse({"message": "Email sent with ZIP link successfully"})
        except Exception as e:
            return JsonResponse({"error": f"Failed to send email: {str(e)}"}, status=500)

    
class StudentProfileLogsView(View):
    REQUIRED_DOCUMENTS = {
        "Medical Certificate",
        "Covid Vaccination Certificate",
        "Vulnerable Sector Check",
        "CPR or First Aid",
        "Mask Fit Certificate",
        "Experience Document",
        "Basic Life Support"
    }
    OPTIONAL_DOCUMENTS = {""}

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        is_approver = Approver.objects.filter(user=request.user).exists()
        is_superuser = request.user.is_superuser

        filter_status = "completed"
        search_query = request.GET.get("search", "").strip().lower()

        # Filters
        gender_filter = request.GET.get("gender", "")
        stage_filter = request.GET.get("stage", "")
        experience_level_filter = request.GET.get("experience_level", "")
        completed_filter = request.GET.get("is_completed")  # "true"/"false"/None
        shift_requested_filter = request.GET.get("shift_requested", "")
        assigned_facility_filter = request.GET.get("assigned_facility", "")
        orientation_date_filter = request.GET.get("orientation_date", "")

        if is_approver:
            profiles = PlacementProfile.objects.prefetch_related('documents').all()
            has_profile = False  # Approvers aren't students
        else:
            profiles = PlacementProfile.objects.select_related('assigned_facility', 'orientation_date')\
                .filter(user=request.user).prefetch_related('documents')
            has_profile = profiles.exists()

        filtered_profile_details = []
        for profile in profiles:
            # Apply search query
            if search_query:
                full_name = f"{profile.first_name} {profile.last_name}".lower()
                email = profile.college_email.lower()
                try:
                    student_id = profile.user.student_id_record.student_id.lower()
                except StudentID.DoesNotExist:
                    student_id = ""

                if search_query not in full_name and search_query not in email and search_query not in student_id:
                    continue

            # Apply filters
            if gender_filter and profile.gender != gender_filter:
                continue
            if stage_filter and profile.stage != stage_filter:
                continue
            if experience_level_filter and profile.experience_level != experience_level_filter:
                continue
            if shift_requested_filter and profile.shift_requested != shift_requested_filter:
                continue

            if assigned_facility_filter and (not profile.assigned_facility or profile.assigned_facility.name != assigned_facility_filter):
                continue
            orientation_date_obj = None

            if orientation_date_filter:
                try:
                    orientation_date_obj = datetime.strptime(orientation_date_filter, '%Y-%m-%d').date()
                except ValueError:
                    orientation_date_obj = None  
            if orientation_date_obj and (not profile.orientation_date or profile.orientation_date.orientation_date != orientation_date_obj):
                continue

            # Check document completeness
            documents = {doc.document_type: doc for doc in profile.documents.all()}
            complete = True
            for doc_type in self.REQUIRED_DOCUMENTS:
                # Skip "Experience Document" if experience_level is "No Experience"
                if doc_type == "Experience Document" and profile.experience_level == "No Experience":
                    continue

                doc = documents.get(doc_type)
                if not doc or not doc.file_name:
                    complete = False
                    break

                # latest_approval = ApprovalLog.objects.filter(document=doc).order_by('-timestamp').first()
                # if not latest_approval or latest_approval.action != "Approved":
                #     complete = False
                #     break

            if completed_filter == "true" and not complete:
                continue
            if completed_filter == "false" and complete:
                continue

            # # Skip profiles based on filter status
            if is_approver:
                if (filter_status == "completed" and not complete) or (filter_status == "incomplete" and complete):
                    continue

            # Prepare document data
            document_details = []
            
            latest_approved_log = None
            approved_count = 0
            for doc in profile.documents.all():
                latest_approval = ApprovalLog.objects.filter(document=doc, action="Approved").order_by('-timestamp').first()
                if latest_approval:
                    approved_count += 1
                    if not latest_approved_log or latest_approval.timestamp > latest_approved_log.timestamp:
                        latest_approved_log = latest_approval

                approval_logs = ApprovalLog.objects.filter(document=doc)
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
                    'id': doc.id,
                    'status': doc.status,
                    'document_type': doc.document_type,
                    'file': doc.file.url if doc.file else None,
                    'rejection_reason': doc.rejection_reason,
                    'uploaded_at': doc.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                    'approval_logs': approver_actions
                })
            
            processed_by = latest_approved_log.approver.full_name if latest_approved_log and latest_approved_log.approver else "N/A"
            # Append profile info
            student_id = ''
            assigned_facility = ''
            try:
                student_id = profile.user.student_id_record.student_id
                assigned_facility = profile.assigned_facility.name if profile.assigned_facility else 'N/A'
            except StudentID.DoesNotExist:
                pass
            document_upload_status = {}
            for doc_type in self.REQUIRED_DOCUMENTS:
                if doc_type == "Experience Document" and profile.experience_level == "No Experience":
                    continue

                doc = documents.get(doc_type)
                document_upload_status[doc_type] = bool(doc and doc.file)

                
            missing_documents = []
            for doc_type in self.REQUIRED_DOCUMENTS:
                if doc_type == "Experience Document" and profile.experience_level == "No Experience":
                    continue

                doc = documents.get(doc_type)
                if not doc or not doc.file_name:
                    missing_documents.append(doc_type)

            # Evaluate Skills Passbook Result
            skills_passbook_result = "Not Uploaded"
            skills_doc = documents.get("Skills Passbook")
            if skills_doc and skills_doc.file_name:
                latest_approval = ApprovalLog.objects.filter(document=skills_doc).order_by('-timestamp').first()
                if latest_approval and latest_approval.action == "Approved":
                    skills_passbook_result = "Approved"
                else:
                    skills_passbook_result = "Uploaded"
            # Evaluate Experience Document Result
            experience_document_result = "Not Uploaded"
            experience_doc = documents.get("Experience Document")
            if experience_doc and experience_doc.file_name:
                latest_approval = ApprovalLog.objects.filter(document=experience_doc).order_by('-timestamp').first()
                if latest_approval and latest_approval.action == "Approved":
                    experience_document_result = "Approved"
                else:
                    experience_document_result = "Uploaded"
                
            filtered_profile_details.append({
                'profile_id': profile.id,
                'first_name': profile.first_name,
                'last_name': profile.last_name,
                'college_email': profile.college_email,
                'student_id': student_id,
                'assigned_facility': assigned_facility,
                'experience_level': profile.experience_level,
                'shift_requested': profile.shift_requested,
                'preferred_facility_name': profile.preferred_facility_name,
                'preferred_facility_address': profile.preferred_facility_address,
                'preferred_facility_contact_person': profile.preferred_facility_contact_person,
                'official_start_date': profile.official_start_date,
                'required_hours': profile.required_hours,
                'document_upload_status': document_upload_status,
                'exact_placement_end_date': profile.exact_placement_end_date,
                'assigned_facility': profile.assigned_facility.name if profile.assigned_facility else 'N/A',
                'orientation_date': profile.orientation_date.orientation_date if profile.orientation_date else 'Not Scheduled',
                'apt_house_no': profile.apt_house_no,
                'street': profile.street,
                'city': profile.city,
                'province': profile.province,
                'postal_code': profile.postal_code,
                'open_to_outside_city': profile.open_to_outside_city,
                'employer_letter': profile.employer_letter.url if profile.employer_letter else None,
                'city_preference_1': profile.city_preference_1,
                'city_preference_2': profile.city_preference_2,
                'stage': profile.stage,
                'facility_feedback': profile.facility_feedback,
                'college_feedback': profile.college_feedback,
                'module_completed': profile.module_completed,
                'notes': profile.notes,
                'date_completed': profile.date_completed,
                'required_hours': profile.required_hours,
                'time_period': profile.time_period,
                'days': profile.days,
                'created_at': profile.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                'module_completed': profile.module_completed,
                'pregnancy_waiver_check': profile.pregnancy_waiver_check,
                'gender': profile.gender,
                'facility_email_address': profile.facility_email_address,
                'documents': document_details,
                'is_completed': complete,
                'processed_by': processed_by,
                'approved_documents_count': approved_count,
                'missing_documents': missing_documents,
                'skills_passbook_result': skills_passbook_result,
                'experience_document_result': experience_document_result,
            })
        # Pagination (10 items per page)
        paginator = Paginator(filtered_profile_details, 10)
        page_number = request.GET.get("page", 1)
        page_obj = paginator.get_page(page_number)
        facilities = Facility.objects.values_list('name', flat=True).distinct()
        orientation_dates = OrientationDate.objects.values_list('orientation_date', flat=True).distinct().order_by('orientation_date')
        return render(request, 'student_profile_logs.html', {
            'page_obj': page_obj,
            'profile_details': page_obj.object_list,
            'is_approver': is_approver,
            'is_superuser': is_superuser,
            'filter_status': filter_status,
            'search_query': search_query,
            'has_profile': has_profile,
            'facilities': facilities,   
            'orientation_dates': orientation_dates,
            'filters': {
                'gender': gender_filter,
                'stage': stage_filter,
                'experience_level': experience_level_filter,
                'is_completed': completed_filter,
                'shift_requested': shift_requested_filter,
                'assigned_facility': assigned_facility_filter,
                'orientation_date': orientation_date_filter,
            }
        })


class StudentIncompleteProfileLogsView(View):
    REQUIRED_DOCUMENTS = {
        "Medical Certificate",
        "Covid Vaccination Certificate",
        "Vulnerable Sector Check",
        "CPR or First Aid",
        "Mask Fit Certificate",
        "Experience Document",
        "Basic Life Support"
    }
    OPTIONAL_DOCUMENTS = {""}

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        is_approver = Approver.objects.filter(user=request.user).exists()
        is_superuser = request.user.is_superuser

        filter_status = request.GET.get("status", "incomplete")
        search_query = request.GET.get("search", "").strip().lower()

        # Filters
        gender_filter = request.GET.get("gender", "")
        stage_filter = request.GET.get("stage", "")
        experience_level_filter = request.GET.get("experience_level", "")
        completed_filter = request.GET.get("is_completed")  # "true"/"false"/None
        shift_requested_filter = request.GET.get("shift_requested", "")
        assigned_facility_filter = request.GET.get("assigned_facility", "")
        orientation_date_filter = request.GET.get("orientation_date", "")

        if is_approver:
            profiles = PlacementProfile.objects.prefetch_related('documents').all()
            has_profile = True
        else:
            profiles = PlacementProfile.objects.select_related('assigned_facility', 'orientation_date')\
                .filter(user=request.user).prefetch_related('documents')
            has_profile = profiles.exists()

        users_no_profile = User.objects.exclude(id__in=PlacementProfile.objects.values_list('user', flat=True))

        if filter_status == "usersNoProfile":
            filtered_profile_details = [
                {
                    'profile_id': user.id,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'college_email': user.email,
                }
                for user in users_no_profile
            ]
            return render(request, 'student_profile_logs.html', {
                'profile_details': filtered_profile_details,
                'is_approver': is_approver,
                'is_superuser': is_superuser,
                'filter_status': filter_status,
                'search_query': search_query,
                'has_profile': has_profile,
                'only_users_no_profile': True,
            })

        filtered_profile_details = []

        for profile in profiles:
            # Apply search
            if search_query:
                full_name = f"{profile.first_name} {profile.last_name}".lower()
                email = profile.college_email.lower()
                try:
                    student_id = profile.user.student_id_record.student_id.lower()
                except StudentID.DoesNotExist:
                    student_id = ""

                if search_query not in full_name and search_query not in email and search_query not in student_id:
                    continue

            if gender_filter and profile.gender != gender_filter:
                continue
            if stage_filter and profile.stage != stage_filter:
                continue
            if experience_level_filter and profile.experience_level != experience_level_filter:
                continue
            if shift_requested_filter and profile.shift_requested != shift_requested_filter:
                continue

            if assigned_facility_filter and (not profile.assigned_facility or profile.assigned_facility.name != assigned_facility_filter):
                continue
            orientation_date_obj = None

            if orientation_date_filter:
                try:
                    orientation_date_obj = datetime.strptime(orientation_date_filter, '%Y-%m-%d').date()
                except ValueError:
                    orientation_date_obj = None  
            if orientation_date_obj and (not profile.orientation_date or profile.orientation_date.orientation_date != orientation_date_obj):
                continue

            # Check document completeness
            documents = {doc.document_type: doc for doc in profile.documents.all()}
            complete = True
            for doc_type in self.REQUIRED_DOCUMENTS:
                # Skip "Experience Document" check if experience_level is "No Experience"
                if doc_type == "Experience Document" and profile.experience_level == "No Experience":
                    continue

                doc = documents.get(doc_type)
                if not doc or not doc.file or not doc.file_name:
                    complete = False
                    break

            if completed_filter == "true" and not complete:
                continue
            if completed_filter == "false" and complete:
                continue

            if (filter_status == "completed" and not complete) or (filter_status == "incomplete" and complete):
                continue

            # Prepare document data
            document_details = []
            latest_approved_log = None
            approved_count = 0
            for doc in profile.documents.all():
                latest_approval = ApprovalLog.objects.filter(document=doc, action="Approved").order_by('-timestamp').first()
                if latest_approval:
                    approved_count += 1
                    if not latest_approved_log or latest_approval.timestamp > latest_approved_log.timestamp:
                        latest_approved_log = latest_approval

                approval_logs = ApprovalLog.objects.filter(document=doc)
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
                    'id': doc.id,
                    'status': doc.status,
                    'document_type': doc.document_type,
                    'file': doc.file.url if doc.file else None,
                    'rejection_reason': doc.rejection_reason,
                    'uploaded_at': doc.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                    'approval_logs': approver_actions
                })
            
            processed_by = latest_approved_log.approver.full_name if latest_approved_log and latest_approved_log.approver else "N/A"
            student_id = ''
            assigned_facility = ''
            try:
                student_id = profile.user.student_id_record.student_id
                assigned_facility = profile.assigned_facility.name if profile.assigned_facility else 'N/A'
            except StudentID.DoesNotExist:
                pass
            document_upload_status = {}
            for doc_type in self.REQUIRED_DOCUMENTS:
                doc = documents.get(doc_type)
                document_upload_status[doc_type] = bool(doc and doc.file)
            filtered_profile_details.append({
                'profile_id': profile.id,
                'first_name': profile.first_name,
                'last_name': profile.last_name,
                'college_email': profile.college_email,
                'apt_house_no': profile.apt_house_no,
                'street': profile.street,
                'city': profile.city,
                'province': profile.province,
                'postal_code': profile.postal_code,
                'document_upload_status': document_upload_status,
                'student_id': student_id,
                'assigned_facility': assigned_facility,
                'open_to_outside_city': profile.open_to_outside_city,
                'experience_level': profile.experience_level,
                'shift_requested': profile.shift_requested,
                'preferred_facility_name': profile.preferred_facility_name,
                'preferred_facility_address': profile.preferred_facility_address,
                'preferred_facility_contact_person': profile.preferred_facility_contact_person,
                'city_preference_1': profile.city_preference_1,
                'city_preference_2': profile.city_preference_2,
                'assigned_facility': profile.assigned_facility.name if profile.assigned_facility else 'N/A',
                'orientation_date': profile.orientation_date.orientation_date if profile.orientation_date else 'Not Scheduled',
                'stage': profile.stage,
                'official_start_date': profile.official_start_date,
                'exact_placement_end_date': profile.exact_placement_end_date,
                'facility_feedback': profile.facility_feedback,
                'college_feedback': profile.college_feedback,
                'notes': profile.notes,
                'date_completed': profile.date_completed,
                'required_hours': profile.required_hours,
                'time_period': profile.time_period,
                'days': profile.days,
                'created_at': profile.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                'module_completed': profile.module_completed,
                'pregnancy_waiver_check': profile.pregnancy_waiver_check,
                'gender': profile.gender,
                'facility_email_address': profile.facility_email_address,
                'documents': document_details,
                'is_completed': complete,
                'processed_by': processed_by,
                'approved_documents_count': approved_count,
            })

        # Pagination (10 items per page)
        paginator = Paginator(filtered_profile_details, 10)
        page_number = request.GET.get("page", 1)
        page_obj = paginator.get_page(page_number)
        facilities = Facility.objects.values_list('name', flat=True).distinct()
        orientation_dates = OrientationDate.objects.values_list('orientation_date', flat=True).distinct().order_by('orientation_date')

        return render(request, 'student_incomplete_profile_logs.html', {
            'page_obj': page_obj,
            'profile_details': page_obj.object_list,
            'is_approver': is_approver,
            'is_superuser': is_superuser,
            'filter_status': filter_status,
            'search_query': search_query,
            'has_profile': has_profile,
            'facilities': facilities,   
            'orientation_dates': orientation_dates,
            'filters': {
                'gender': gender_filter,
                'stage': stage_filter,
                'experience_level': experience_level_filter,
                'is_completed': completed_filter,
                'shift_requested': shift_requested_filter,
                'assigned_facility': assigned_facility_filter,
                'orientation_date': orientation_date_filter,
            }
        })



@user_passes_test(lambda u: u.is_superuser)  # Only allow superusers
def delete_profile(request, profile_id):
    # Get the profile to delete
    profile = get_object_or_404(PlacementProfile, id=profile_id)
    
    # Delete associated document files
    for document in profile.documents.all():
        if document.file:
            document.file.delete(save=False)  # Deletes the file from storage without saving the model
        document.delete()  # Delete the Document record from the database

    # Optionally, if there are other related objects that need special deletion, handle them here

    # Get the associated user before deleting the profile.
    user = profile.user

    # Delete the profile.
    profile.delete()

    # Delete the associated user.
    user.delete()

    return JsonResponse({'message': 'Profile, associated documents (with files) and user deleted successfully!'})

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

        # If approved and document type is Experience Document, update required_hours
        if action == DocumentStatus.APPROVED.value and document.document_type == "Experience Document":
            document.profile.required_hours = 200
            document.profile.save()

        # Send placement notification
        message = f"Your document '{document.document_type}' has been {action.lower()}."
        if action == DocumentStatus.REJECTED.value:
            message += f" Reason: {rejection_reason}"

        PlacementNotification.objects.create(
            profile=document.profile,
            subject=f"Document {action}: {document.document_type}",
            message=message
        )

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
    subject = 'Placement: Settle Tuition Fee Balance'
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
            img {{
                width: 240px;
                height: 90px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <p>Greetings!</p>
            <p>Thank you for creating your Placement! You still have an outstanding balance. Please pay your tuition fee to avoid any delays in the process. This will help us move forward smoothly with your placement.</p>
            <h3>Payment Options:</h3>
            <ul>
                <li>E-Transfer to: <span class="highlight">payment@peakcollege.ca</span></li>
                <li>Cash, Credit, or Debit Payment on Campus</li>
            </ul>
            <p><span class="bold">School Office Hours:</span></p>
            <p><span class="bold">Monday to Thursday:</span> 9:00 AM to 5:00PM</p>
            <p><span class="bold">Saturday:</span> 9:30 AM to 4:00 PM</p>
            <div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement at Peak College!</p>
                <span>Warm regards, </span>
                <br>
                <span> The Peak Healthcare Team</span>
                <br>
                <span>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></span>
                <br>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
                <br>
                <span>1140 Sheppard Ave West</span>
                <br>
                <span>Unit #12, North York, ON</span>
                <br>
                <span>M3K 2A2</span>
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
    
def get_document_file_paths(documents):
    file_path = documents[0].file.name 

    full_url = f"http://placement.peakcollege.ca/documents/{file_path}"
    
    return full_url

    
def send_email_notify_resume(profile, documents, student_id):
    file_url = get_document_file_paths(documents)

    subject = 'Resume Uploaded'
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
            img {{
                width: 240px;
                height: 90px;
            }}
        </style>
    </head>
    <body style="font-family: Arial, sans-serif; padding: 20px; color: #333;">
        <p>Resume of <strong>{student_id} {profile.first_name} {profile.last_name}</strong> is now available in Google Drive.</p>
        
        <p>
            <a href="{file_url}" target="_blank" style="
                display: inline-block;
                padding: 12px 24px;
                background-color: #008080;
                color: white;
                text-decoration: none;
                border-radius: 6px;
                font-weight: bold;
                margin-top: 15px;
            ">View File(s)</a>
        </p>
<div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement at Peak College!</p>
                <span>Warm regards, </span>
                <br>
                <span> The Peak Healthcare Team</span>
                <br>
                <span>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></span>
                <br>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
                <br>
                <span>1140 Sheppard Ave West</span>
                <br>
                <span>Unit #12, North York, ON</span>
                <br>
                <span>M3K 2A2</span>
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

def send_email_notify_skills_passbook(profile, documents, student_id):
    file_url = get_document_file_paths(documents)

    subject = 'Skills Passbook Uploaded'
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
            img {{
                width: 240px;
                height: 90px;
            }}
        </style>
    </head>
    <body style="font-family: Arial, sans-serif; padding: 20px; color: #333;">
        <p>Skills Passbook of <strong>{student_id} {profile.first_name} {profile.last_name}</strong> is now available in Google Drive.</p>
        
        <p>
            <a href="{file_url}" target="_blank" style="
                display: inline-block;
                padding: 12px 24px;
                background-color: #008080;
                color: white;
                text-decoration: none;
                border-radius: 6px;
                font-weight: bold;
                margin-top: 15px;
            ">View File(s)</a>
        </p>
<div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement at Peak College!</p>
                <span>Warm regards, </span>
                <br>
                <span> The Peak Healthcare Team</span>
                <br>
                <span>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></span>
                <br>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
                <br>
                <span>1140 Sheppard Ave West</span>
                <br>
                <span>Unit #12, North York, ON</span>
                <br>
                <span>M3K 2A2</span>
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

    
def send_email_notify_placement(profile, facility, orientation_date, requested_hours, sender_name):
    subject = 'Important: Placement Orientation'

    # HTML content
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
                font-weight: bold;
            }}
            ul {{
                padding-left: 20px;
            }}
            li {{
                margin-bottom: 8px;
            }}
            img {{
                width: 240px;
                height: 90px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <p>Dear {profile.first_name},</p>
            <p>Good day!<br>Please see the information below and read carefully.</p>
            
            <p><span class="highlight">Assigned Facility:</span><br>
            {facility.name}<br>
            {facility.address}<br>
            Phone No.: {facility.facility_phone}</p>

            <p><span class="highlight">Orientation Date:</span> {orientation_date}</p>
            <p><span class="highlight">Requested Hours:</span> {requested_hours} Hours</p>

            <p><span class="highlight">Kindly observe the following during your placement:</span></p>
            <ul>
                <li>Be there at least 15 minutes prior to your scheduled time.</li>
                <li>Wear proper uniform and proper shoes.</li>
                <li>Display your Student ID or name tag.</li>
                <li>Facilities are scent-free; only use unscented products.</li>
                <li>Cell phones are not permitted during work hours.</li>
                <li>If you are feeling unwell, kindly follow the facility’s policy.</li>
                <li>Bring your skills passbook to log your hours and have it evaluated at the end.</li>
            </ul>

            <p>Remember to follow the directives of your preceptor. If unclear, always ask.</p>

            <p><span class="highlight">Other important matters:</span></p>
            <ol>
                <li>Placement Key Points: <a href="#">Click here</a>.</li>
                <li>After your placement, scan and upload your timesheet and passbook here: <a href="#">Click here</a>.</li>
                <li>Reply to this email to confirm you’ve read and understood the contents.</li>
            </ol>

            <p>For questions, email <a href="mailto:placement@peakcollege.ca">placement@peakcollege.ca</a> or call (416) 756-4846 ext:
            <br>Grace Doton - 106
            <br>Rey Bautista - 107
            <br>Dave Mangilet - 105</p>

            <div class="footer">
                <p>Thank you, and best wishes for your Clinical Placement journey!</p>
                <p>Warm regards,<br>{sender_name}<br>Placement Department<br>Email: <a href="mailto:placement@peakcollege.ca">placement@peakcollege.ca</a></p>
                <br>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg" alt="Peak College Logo">
                <br>
                1140 Sheppard Ave West, Unit #12, North York, ON M3K 2A2
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


def send_email_notify_result(profile, rejected_documents, zip_url):
    subject = 'Placement: Resubmit Rejected Documents'

    # Build the dynamic list of rejected documents
    document_list_html = ""
    for doc in rejected_documents:
        reason = doc.rejection_reason if doc.rejection_reason else "No reason provided"
        document_list_html += f"<li><span class='bold'>{doc.document_type}:</span> {reason}</li>"

    # HTML Email message
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
                width: 240px;
                height: 90px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <p>Greetings!</p>
            <p>The documents below were rejected due to the following reasons:</p>
            <ul>
                {document_list_html}
            </ul>
            <p>Next step: address the reasons and resubmit the documents by clicking the link below.</p>
            <p><a href="https://www.peakcollege.ca" class="highlight">Resubmission Link: Click here!</a></p>
            <p>You’ll receive another email once all are approved.</p>
            <div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement at Peak College!</p>
                <span>Warm regards, </span>
                <br>
                <span> The Peak Healthcare Team</span>
                <br>
                <span>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></span>
                <br>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
                <br>
                <span>1140 Sheppard Ave West</span>
                <br>
                <span>Unit #12, North York, ON</span>
                <br>
                <span>M3K 2A2</span>
            </div>
        </div>
    </body>
    </html>
    """

    print("Sending email to:", profile.college_email)  # Debugging line
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [profile.college_email],
        html_message=message
    )

def send_email_done(profile, documents):
    subject = f'{profile.first_name} {profile.last_name} - Placement: Documents Approved'
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
            img {{
                width: 240px;
                height: 90px;
            }}
</style>
</head>
<body>
<div class="container">
<p>Greetings!</p>
<p>All your documents are now <span class="highlight">APPROVED</span>.</p>
<p>The Placement Coordinator: We will reach out to you through email or phone call. Once you finalize with her which facility you’re going to do your placement, she will inform you of your Placement Orientation Date.</p>
<p>Then you can pick up your Skills Passbook and NACC Reviewer from the school on any operating day.</p>
<p><span class="bold">School Office Hours:</span></p>
<p><span class="bold">Monday to Thursday:</span> 9:00 AM to 5:00PM</p>
<p><span class="bold">Saturday:</span> 9:30 AM to 4:00 PM</p>
<div class="footer">
<p>Best of luck with your placement process and thanks again for completing your Placement Profile at Peak College!</p>
<span>Warm regards, </span>
<br>
<span> The Peak Healthcare Team</span>
<br>
<span>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></span>
<br>
<img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
<br>
<span>1140 Sheppard Ave West</span>
<br>
<span>Unit #12, North York, ON</span>
<br>
<span>M3K 2A2</span>
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
 
 
    email.send()

def send_placement_email(profile):
    subject = f'{profile.first_name} {profile.last_name} - Placement Completed'
    message = f'''
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; background-color: #f9f9f9; padding: 20px; }}
            .container {{ background-color: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); }}
            h2 {{ color: #008080; }}
            p {{ font-size: 16px; line-height: 1.5; }}
            .footer {{
                margin-top: 20px;
                font-size: 14px;
                color: #555;
            }}
            .footer a {{
                color: #008080;
                text-decoration: none;
            }}
            img {{
                width: 240px;
                height: 90px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>{profile.first_name} {profile.last_name} is now ready for placement.</h2>
            
        </div>
        <div class="footer">
<p>Best of luck with your placement process and thanks again for completing your Placement Profile at Peak College!</p>
<span>Warm regards, </span>
<br>
<span> The Peak Healthcare Team</span>
<br>
<span>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></span>
<br>
<img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
<br>
<span>1140 Sheppard Ave West</span>
<br>
<span>Unit #12, North York, ON</span>
<br>
<span>M3K 2A2</span>
</div>
    </body>
    </html>
'''
    email = EmailMessage(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        ['placement@peakcollege.ca']
    )
    email.content_subtype = "html"
 
    email.send()

def send_documents_email(profile, documents, zip_url):
    subject = f'{profile.first_name} {profile.last_name} - Documents Completed'
    message = f'''
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; background-color: #f9f9f9; padding: 20px; }}
            .container {{ background-color: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); }}
            h2 {{ color: #008080; }}
            p {{ font-size: 16px; line-height: 1.5; }}
            .footer {{
                margin-top: 20px;
                font-size: 14px;
                color: #555;
            }}
            .footer a {{
                color: #008080;
                text-decoration: none;
            }}
            img {{
                width: 240px;
                height: 90px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>{profile.first_name}'s Complete Files for Placement</h2>
            <p>(Note: Attach all submitted documents)</p>
            <p>You can find the documents in the following ZIP file:</p>
            <p><a href="http://placement.peakcollege.ca{zip_url}">Download Documents</a></p>
        </div>
        <div class="footer">
<p>Best of luck with your placement process and thanks again for completing your Placement Profile at Peak College!</p>
<span>Warm regards, </span>
<br>
<span> The Peak Healthcare Team</span>
<br>
<span>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></span>
<br>
<img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
<br>
<span>1140 Sheppard Ave West</span>
<br>
<span>Unit #12, North York, ON</span>
<br>
<span>M3K 2A2</span>
</div>
    </body>
    </html>
    '''
    
    email = EmailMessage(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        ['documents@peakcollege.ca']
    )
    email.content_subtype = "html"
 
    email.send()


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
            img {{
                width: 240px;
                height: 90px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <p>Greetings!</p>
            <p>The student <span class="bold">{profile.first_name} {profile.last_name}</span> has resubmitted the corrected documents for your review.</p>
            <p>Click the link below to assess (approve or reject) the submission:</p>
            <p><a href="https://www.peakcollege.ca/approver-view" class="highlight">Approver's View: Click here to log in!</a></p>
            <p>Please review and take the necessary action.</p>
            <div class="footer">
                <p>Best of luck with your placement process and thanks again for completing your Placement at Peak College!</p>
                <span>Warm regards, </span>
                <br>
                <span> The Peak Healthcare Team</span>
                <br>
                <span>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></span>
                <br>
                <img src="http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg"></img>
                <br>
                <span>1140 Sheppard Ave West</span>
                <br>
                <span>Unit #12, North York, ON</span>
                <br>
                <span>M3K 2A2</span>
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

        if action == 'notify_result':
            zip_file_name = f"{profile.id}_{profile.first_name}_{profile.last_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            zip_file_path = os.path.join(settings.MEDIA_ROOT, 'documents', 'uploads', zip_file_name)

            with zipfile.ZipFile(zip_file_path, 'w') as zipf:
                for document in documents:
                    if document.file and document.file.name: 
                        try:
                            zipf.write(document.file.path, os.path.basename(document.file.name))
                        except Exception as e:
                            continue  
            zip_url = os.path.join(settings.MEDIA_URL, 'documents', 'uploads', zip_file_name)

            rejected_documents = documents.filter(status="Rejected")
            send_email_notify_result(profile, rejected_documents, zip_url=zip_url)

        elif action == 'remind_fee':
            send_email_remind_fee(profile)
        elif action == 'done':
            zip_file_name = f"{profile.id}_{profile.first_name}_{profile.last_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            zip_file_path = os.path.join(settings.MEDIA_ROOT, 'documents', 'uploads', zip_file_name)

            with zipfile.ZipFile(zip_file_path, 'w') as zipf:
                for document in documents:
                    if document.file and document.file.name:
                        try:
                            zipf.write(document.file.path, os.path.basename(document.file.name))
                        except Exception:
                            continue
            
            zip_url = os.path.join(settings.MEDIA_URL, 'documents', 'uploads', zip_file_name)
            send_email_done(profile, documents)
            send_placement_email(profile)
            send_documents_email(profile, documents, zip_url=zip_url)
        elif action == 'resubmit':
            send_email_resubmit(profile, documents)
        elif action == 'notify_placement':
            facility = profile.assigned_facility
            orientation_date = profile.orientation_date.orientation_date.strftime("%B %d, %Y") if profile.orientation_date else "Not Scheduled"
            requested_hours = profile.required_hours or 300
            sender_name = request.user.get_full_name() or request.user.username

            send_email_notify_placement(profile, facility, orientation_date, requested_hours, sender_name)

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
    # Exclude superusers only
    users = User.objects.exclude(is_superuser=True)

    approvers_data = []

    for user in users:
        try:
            # If the user has an approver profile, show as Approver
            approver = user.approver_profile
            approvers_data.append({
                'user': user,
                'role': 'Approver',
                'full_name': approver.full_name,
                'position': approver.position,
            })
        except Approver.DoesNotExist:
            # Otherwise, show as Student
            approvers_data.append({
                'user': user,
                'role': 'Student',
                'full_name': user.get_full_name() or user.username,
                'position': '',
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
        
        try:
            student_id = profile.user.student_id_record.student_id
        except StudentID.DoesNotExist:
            student_id = None 
        print(document_type, "document type")
        if document_type == "Resume":
            send_email_notify_resume(profile, [new_document], student_id=student_id)
        elif document_type == "Skills Passbook":
            send_email_notify_skills_passbook(profile, [new_document], student_id=student_id)

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

@login_required
def incomplete_profiles_view(request):
    incomplete_profiles = []

    profiles = PlacementProfile.objects.all().prefetch_related("documents")
    for profile in profiles:
        required_docs = [
            "Medical Certificate",
            "Covid Vaccination Certificate",
            "Vulnerable Sector Check",
            "CPR or First Aid",
            "Mask Fit Certificate"
        ]
        documents = {doc.document_type: doc for doc in profile.documents.all()}
        complete = True

        for doc_type in required_docs:
            doc = documents.get(doc_type)
            if not doc:
                complete = False
                break
            latest_approval = ApprovalLog.objects.filter(document=doc).order_by('-timestamp').first()
            if not latest_approval or latest_approval.action != "Approved":
                complete = False
                break

        if not complete:
            incomplete_profiles.append(profile)

    return render(request, 'incomplete_profiles.html', {'profiles': incomplete_profiles})


@login_required
def complete_profiles_view(request):
    complete_profiles = []

    profiles = PlacementProfile.objects.all().prefetch_related("documents")
    for profile in profiles:
        required_docs = [
            "Medical Certificate",
            "Covid Vaccination Certificate",
            "Vulnerable Sector Check",
            "CPR or First Aid",
            "Mask Fit Certificate"
        ]
        documents = {doc.document_type: doc for doc in profile.documents.all()}
        complete = True

        for doc_type in required_docs:
            doc = documents.get(doc_type)
            if not doc:
                complete = False
                break
            latest_approval = ApprovalLog.objects.filter(document=doc).order_by('-timestamp').first()
            if not latest_approval or latest_approval.action != "Approved":
                complete = False
                break

        if complete:
            complete_profiles.append(profile)

    return render(request, 'complete_profiles.html', {'profiles': complete_profiles})


#write a delete user function access only to super user 
@user_passes_test(lambda u: u.is_superuser)
def delete_user(request, user_id):
    if request.method == 'POST':
        try:
            user = get_object_or_404(User, id=user_id)
            user.delete()
            messages.success(request, 'User deleted successfully!')
        except Exception as e:
            messages.error(request, f'Error deleting user: {str(e)}')
    return redirect('pending_users') 


@user_passes_test(superuser_required, login_url='/404/')
def get_users_without_profiles_view(request):
    profile_user_ids = PlacementProfile.objects.values_list('user', flat=True)
    approver_user_ids = Approver.objects.values_list('user', flat=True)

    users = User.objects.exclude(id__in=profile_user_ids).exclude(id__in=approver_user_ids)
    return render(request, 'users_without_profiles.html', {'users': users})

# Facility Views
class FacilityListView(ListView):
    model = Facility
    template_name = 'facility_list.html'
    context_object_name = 'facilities'

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.GET.get('status')
        province = self.request.GET.get('province')
        city = self.request.GET.get('city')

        # Apply filters if they exist
        if status:
            queryset = queryset.filter(status=status)
        if province:
            queryset = queryset.filter(province=province)
        if city:
            queryset = queryset.filter(city=city)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get distinct provinces and cities
        provinces = list(set(Facility.objects.values_list('province', flat=True)))

        cities = list(set(Facility.objects.values_list('city', flat=True)))

        context['provinces'] = provinces
        context['cities'] = cities
        return context

class FacilityCreateView(CreateView):
    model = Facility
    form_class = FacilityForm
    template_name = 'facility_list.html'
    success_url = reverse_lazy('facility_list')

def update_facility(request, pk):
    facility = get_object_or_404(Facility, pk=pk)
    
    if request.method == 'POST':
        form = FacilityForm(request.POST, instance=facility)
        if form.is_valid():
            form.save()

            # Return JSON if it's an AJAX request (like from fetch)
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            else:
                return redirect('facility_list')  # Non-AJAX fallback
        else:
            # If form is invalid, return errors as JSON for AJAX
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    
    # Render the form normally if GET
    return render(request, 'update_facility.html', {'form': form, 'facility': facility})

class FacilityDeleteView(DeleteView):
    model = Facility
    success_url = reverse_lazy('facility_list')

    # Directly delete the object and redirect on GET request
    def get(self, request, *args, **kwargs):
        facility = self.get_object()
        facility.delete()
        return redirect(self.success_url)

# OrientationDate Views
class OrientationDateListView(ListView):
    model = OrientationDate
    template_name = 'orientation_list.html'
    context_object_name = 'orientations'

class OrientationDateCreateView(CreateView):
    model = OrientationDate
    form_class = OrientationDateForm
    success_url = reverse_lazy('orientation_list')

class OrientationDateUpdateView(UpdateView):
    model = OrientationDate
    form_class = OrientationDateForm
    success_url = reverse_lazy('orientation_list')

class OrientationDateDeleteView(DeleteView):
    model = OrientationDate
    success_url = reverse_lazy('orientation_list')

    # Directly delete the object and redirect on GET request
    def get(self, request, *args, **kwargs):
        orientation_date = self.get_object()
        orientation_date.delete()
        return redirect(self.success_url)

def edit_facility(request, facility_id):
    facility = get_object_or_404(Facility, pk=facility_id)
    data = {
        'name': facility.name,
        'status': facility.status,
        'province': facility.province,
        'city': facility.city,
        'address': facility.address,
        'facility_phone': facility.facility_phone,
        'website': facility.website,
        'person_in_charge': facility.person_in_charge,
        'email': facility.email,
        'phone_number': facility.phone_number,
        'designation': facility.designation,
        'additional_requirements': facility.additional_requirements,
        'shifts_available': facility.shifts_available,
        'notes': facility.notes,
        'accepted_student_number': facility.accepted_student_number,
'in_placement': facility.in_placement,
'waitlist': facility.waitlist,
    }
    return JsonResponse(data)

from django.db.models import Count, Q


def get_profiles_facilities_orientations():
    required_docs = [
        "Medical Certificate",
        "Covid Vaccination Certificate",
        "Vulnerable Sector Check",
        "Mask Fit Certificate",
        "CPR or First Aid",
        "Experience Document",  # Always required and must be approved
    ]

    # Fetch profiles where all required documents are approved
    profiles = PlacementProfile.objects.select_related(
        'user', 'assigned_facility', 'orientation_date'
    ).annotate(
        num_approved_docs=Count(
            'documents',
            filter=Q(
                documents__document_type__in=required_docs,
                documents__status=DocumentStatus.APPROVED.value,
            )
        )
    ).filter(
        num_approved_docs=len(required_docs)
    )

    # Fetch facilities and orientation dates
    facilities = Facility.objects.filter(status='Active').order_by('name')
    orientation_dates = OrientationDate.objects.order_by('-orientation_date')

    return {
        "profiles": profiles,
        "facilities": facilities,
        "orientation_dates": orientation_dates,
    }

def assign_facility_and_orientation_date_to_users(request):
    context = get_profiles_facilities_orientations()
    return render(request, "assign_facility.html", context)

def assign_facility_view(request):
    if request.method == 'POST':
        user_ids = request.POST.getlist('selected_users')
        facility_id = request.POST.get('facility_id')
        orientation_id = request.POST.get('orientation_id')

        context = get_profiles_facilities_orientations()  # Always load context

        if not user_ids:
            context["error"] = "No users selected."
            return render(request, 'assign_facility.html', context)

        if not facility_id and not orientation_id:
            context["error"] = "Please select at least a facility or orientation date."
            return render(request, 'assign_facility.html', context)

        try:
            facility = Facility.objects.get(id=facility_id) if facility_id else None
            orientation_date = OrientationDate.objects.get(id=orientation_id) if orientation_id else None
        except (Facility.DoesNotExist, OrientationDate.DoesNotExist):
            context["error"] = "Invalid facility or orientation date."
            return render(request, 'assign_facility.html', context)

        profiles = PlacementProfile.objects.filter(user__id__in=user_ids)

        update_fields = {}
        if facility:
            update_fields["assigned_facility"] = facility
        if orientation_date:
            update_fields["orientation_date"] = orientation_date

        if update_fields:
            profiles.update(**update_fields)

        context["success"] = "Assignment updated successfully."
        return render(request, 'assign_facility.html', context)

    return redirect('assign_facility')


def get_cities_and_provinces(request):
    try:
        # Get all cities
        cities = City.objects.all()
        
        # Group cities by province
        city_data = {}
        for city in cities:
            province_name = city.province
            if province_name not in city_data:
                city_data[province_name] = []
            city_data[province_name].append(city.name)
        
        # Return the data as JSON
        return JsonResponse(city_data)
    
    except Exception as e:
        # Log the error for debugging
        print(f"Error occurred: {e}")
        return JsonResponse({'error': 'An error occurred while fetching cities and provinces'}, status=500)
    
def set_official_start_date_view(request, profile_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            start_date = data.get("official_start_date")
            end_date = data.get("end_date")
            module_completed_value = data.get("module_completed")
            print(module_completed_value)

            profile = PlacementProfile.objects.get(id=profile_id)
            profile.official_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            profile.exact_placement_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            profile.module_completed = module_completed_value 
            profile.save()

            return JsonResponse({"status": "success", "message": "Start date and days updated successfully."})

        except PlacementProfile.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Profile not found."})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})
    return JsonResponse({"status": "error", "message": "Invalid request."})

def pregnancy_policy_view(request):
    return render(request, "pregnancy_policy.html")

def get_student_profile_by_id(request, profile_id):
    profile = get_object_or_404(
        PlacementProfile.objects.select_related('assigned_facility', 'orientation_date')
        .prefetch_related('documents'),
        id=profile_id
    )

    REQUIRED_DOCUMENTS = {
        "Medical Certificate",
        "Covid Vaccination Certificate",
        "Vulnerable Sector Check",
        "CPR or First Aid",
        "Mask Fit Certificate",
        "Experience Document"
    }

    documents = {doc.document_type: doc for doc in profile.documents.all()}
    complete = True
    for doc_type in REQUIRED_DOCUMENTS:
        doc = documents.get(doc_type)
        if not doc:
            complete = False
            break
        latest_approval = ApprovalLog.objects.filter(document=doc).order_by('-timestamp').first()
        if not latest_approval or latest_approval.action != "Approved":
            complete = False
            break

    document_details = []
    for doc in profile.documents.all():
        approval_logs = ApprovalLog.objects.filter(document=doc)
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
            'id': doc.id,
            'status': doc.status,
            'document_type': doc.document_type,
            'file': doc.file.url if doc.file else None,
            'rejection_reason': doc.rejection_reason,
            'uploaded_at': doc.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
            'approval_logs': approver_actions
        })

    try:
        student_id = profile.user.student_id_record.student_id
    except StudentID.DoesNotExist:
        student_id = ''

    context = {
        'profile': profile,
        'student_id': student_id,
        'documents': document_details,
        'is_completed': complete
    }

    return render(request, 'student_profile.html', context)

def update_stage(request):
    try:
        data = json.loads(request.body)
        profile_id = data.get('profile_id')
        new_stage = data.get('stage')

        # Ensure stage is valid
        valid_stages = ["DONE", "ENDORSED", "IN_PLACEMENT", "CANCELLED", "TRANSFERRED", "ONHOLD", "ONGOING_PROCESS", "ORIENTATION_SCHEDULED", "READY"]
        if new_stage not in valid_stages:
            return JsonResponse({"success": False, "error": "Invalid stage"}, status=400)

        # Update the stage of the PlacementProfile
        profile = PlacementProfile.objects.get(id=profile_id)
        profile.stage = new_stage
        profile.save()

        return JsonResponse({"success": True})

    except PlacementProfile.DoesNotExist:
        return JsonResponse({"success": False, "error": "Profile not found"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
    
def base_view(request):
    has_profile = PlacementProfile.objects.filter(user=request.user).exists()
    context = {
        'has_profile': has_profile,
    }
    return render(request, 'base.html', context)