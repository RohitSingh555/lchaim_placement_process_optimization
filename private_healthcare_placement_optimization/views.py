from datetime import datetime
import json
import os
import re
import time

import zipfile
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.core.mail import EmailMessage
from django.views import View

from private_healthcare_placement_optimization.templatetags.forms_extras import document_group, allowed_docs, format_long_date
from .models import PlacementProfile, Document, ActionLog
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
from django.utils.decorators import method_decorator

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
    ActionLog
)
from django.views.decorators.http import require_POST, require_GET

from PyPDF2 import PdfMerger

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

        user = request.user
        college_email = user.email 
        first_name = user.first_name
        last_name = user.last_name
        apt_house_no = request.POST.get('apt_house_no')
        street = request.POST.get('street')
        city = request.POST.get('city')
        province = request.POST.get('province')
        postal_code = request.POST.get('postal_code')
        municipality = request.POST.get('municipality')
        open_to_outside_city = request.POST.get('open_to_outside_city') == 'Yes'
        experience_level = request.POST.get('experience_level')
        shift_requested = request.POST.get('shift_requested')
        preferred_facility_name = request.POST.get('preferred_facility_name')
        preferred_facility_address = request.POST.get('preferred_facility_address')
        preferred_facility_contact_person = request.POST.get('preferred_facility_contact_person')
        city_preference_1 = request.POST.get('city_preference_1')
        city_preference_2 = request.POST.get('city_preference_2')
        gender = request.POST.get('gender')
        required_hours = request.POST.get('required_hours')
        if not required_hours:
            if experience_level == 'No Experience':
                required_hours = 300
            elif experience_level in ['1 Year PSW Experience', 'International Nurse', 'Caregiver Experience']:
                required_hours = 200
            else:
                required_hours = None

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
                municipality=municipality,
                open_to_outside_city=open_to_outside_city,
                experience_level=experience_level,
                shift_requested=shift_requested,
                preferred_facility_name=preferred_facility_name,
                preferred_facility_address=preferred_facility_address,
                preferred_facility_contact_person=preferred_facility_contact_person,
                city_preference_1=city_preference_1,
                city_preference_2=city_preference_2,
                gender=gender,
                required_hours=required_hours,
            )
        except Exception as e:
            print(f"Error saving PlacementProfile: {e}")
            return render(request, 'placement_profile_form.html', {'error': 'Failed to save Placement'})

        documents_data = {
            'experience_document': 'Experience Document',
            'medical_certificate_form': 'Medical Report Form',
            'xray_result': 'X-Ray Result',
            'mmr_lab_vax_record': 'MMR Lab/Vax Record',
            'varicella_lab_vax_record': 'Varicella Lab/Vax Record',
            'tdap_vax_record': 'TDAP Vax Record',
            'hepatitis_b_lab_vax_record': 'Hepatitis B Lab/Vax Record',
            'hepatitis_a_lab_vax_record': 'Hepatitis A Lab/Vax Record',
            'covid_vaccination_certificate': 'Covid Vaccination Certificate',
            'vulnerable_sector_check': 'Vulnerable Sector Check',
            'cpr_or_first_aid': 'CPR & First Aid',
            'mask_fit_certificate': 'Mask Fit Certificate',
            'basic_life_support': 'Basic Life Support',
            'flu_shot': 'Flu Shot',
            'resume': 'Resume',
            'extra_dose_of_covid': 'Extra Dose of Covid',
            'other_documents': 'Other Documents',
            'skills_passbook': 'Skills Passbook',
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
                new_file_name = None
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

        required_document_keys = {'medical_certificate_form', 'covid_vaccination_certificate', 'vulnerable_sector_check', 'cpr_or_first_aid', 'mask_fit_certificate', 'experience_document', 'basic_life_support'}
        
        missing_required_docs = [documents_data[key] for key in required_document_keys if key in missing_documents]

        if not missing_required_docs:
            try:                
                messages.error(
                    request, 
                    "Your documents are now <strong>UNDER REVIEW</strong> by our team.<br><br>Next step, wait for the approval of your submitted documents.<br><br>You'll receive another email once all are approved."
                )
                send_welcome_email(profile, submitted_documents)
                print(f"Welcome email sent to {profile.college_email}")
                # Set session flag for popup
                request.session['show_under_review_popup'] = True
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

        # After all documents are uploaded, check for medical requirements
        MEDICAL_REQUIREMENTS = [
            'Medical Report Form',
            'X-Ray Result',
            'MMR Lab/Vax Record',
            'Varicella Lab/Vax Record',
            'TDAP Vax Record',
            'Hepatitis A Lab/Vax Record',
            'Hepatitis B Lab/Vax Record',
        ]
        # Get all medical requirement docs for this profile
        medical_docs = Document.objects.filter(profile=profile, document_type__in=MEDICAL_REQUIREMENTS)
        # Only proceed if all are uploaded and are PDFs
        if medical_docs.count() == len(MEDICAL_REQUIREMENTS) and all(doc.file and doc.file.name.lower().endswith('.pdf') for doc in medical_docs):
            pdf_paths = [doc.file.path for doc in medical_docs]
            safe_first_name = re.sub(r'\W+', '_', first_name or '').strip('_')
            safe_last_name = re.sub(r'\W+', '_', last_name or '').strip('_')
            merged_medical_pdf_name = f"{safe_first_name}_{safe_last_name}_MedCert.pdf"
            merged_medical_pdf_dir = os.path.join(settings.MEDIA_ROOT, "documents", "uploads")
            os.makedirs(merged_medical_pdf_dir, exist_ok=True)
            merged_medical_pdf_path = os.path.join(merged_medical_pdf_dir, merged_medical_pdf_name)
            merge_pdfs(pdf_paths, merged_medical_pdf_path)
            # Save merged file to storage
            with open(merged_medical_pdf_path, 'rb') as f:
                merged_file_content = ContentFile(f.read())
                merged_file_storage_path = default_storage.save(os.path.join("documents/uploads", merged_medical_pdf_name), merged_file_content)
            # Create or update Document entry for merged PDF
            Document.objects.update_or_create(
                profile=profile,
                document_type='Merged Medical Certificate',
                defaults={
                    'file': merged_file_storage_path,
                    'file_name': merged_medical_pdf_name,
                    'status': 'In Review',
                }
            )

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
            <p>Next step, wait for the approval of your submitted documents. You'll receive another email once all are approved.</p>
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




from collections import OrderedDict
class StudentProfileLogsView(View):
    DOCUMENT_GROUP_ORDER = [
    "Experience",
    "Medical Requirements",
    "NACC Requirements",
    "Additional Facility Requirements",
    "Documents Required After Placement Completion"
]

    REQUIRED_DOCUMENTS = {
        "Medical Report Form",
        "Covid Vaccination Certificate",
        "Vulnerable Sector Check",
        "CPR & First Aid",
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
            docs_sorted = sorted(profile.documents.all(), key=lambda d: allowed_docs.index(d.document_type) if d.document_type in allowed_docs else 999)
            latest_approved_log = None
            approved_count = 0
            grouped_documents = OrderedDict((group, []) for group in self.DOCUMENT_GROUP_ORDER)
            
            for doc in docs_sorted:
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
                    'uploaded_at': format_long_date(doc.uploaded_at) if doc.uploaded_at else '-',
                    'updated_at': format_long_date(doc.updated_at) if doc.updated_at else '-',
                    'approved_at': format_long_date(doc.approved_at) if doc.approved_at else '-',
                    'rejected_at': format_long_date(doc.rejected_at) if doc.rejected_at else '-',
                    'uploaded_new_file': getattr(doc, 'uploaded_new_file', False),
                    'version': getattr(doc, 'version', 1),
                    'approval_logs': approver_actions
                })


            all_doc_types = [d.document_type for d in docs_sorted]
            merged_present = 'Merged Medical Certificate' in all_doc_types

            for doc in docs_sorted:
                group = document_group(doc.document_type, all_doc_types)
                if not group:
                    continue  # Skip documents not in any known group

                latest_approval = ApprovalLog.objects.filter(document=doc, action="Approved").order_by('-timestamp').first()
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
                doc_info = {
                    'id': doc.id,
                    'status': doc.status,
                    'document_type': doc.document_type,
                    'file': doc.file.url if doc.file else None,
                    'rejection_reason': doc.rejection_reason,
                    'uploaded_at': format_long_date(doc.uploaded_at) if doc.uploaded_at else '-',
                    'updated_at': format_long_date(doc.updated_at) if doc.updated_at else '-',
                    'approved_at': format_long_date(doc.approved_at) if doc.approved_at else '-',
                    'rejected_at': format_long_date(doc.rejected_at) if doc.rejected_at else '-',
                    'uploaded_new_file': getattr(doc, 'uploaded_new_file', False),
                    'version': getattr(doc, 'version', 1),
                    'approval_logs': approver_actions
                }

                # If merged is present, only add the merged doc to the group, and skip all others
                if group == 'Medical Requirements' and merged_present:
                    if doc.document_type == 'Merged Medical Certificate':
                        grouped_documents[group] = [doc_info]  # Set only once
                    continue  # Skip all other medical docs

                grouped_documents[group].append(doc_info)
            
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
                
            # Action log times
            action_log_times = {}
            for action in ["remind_fee", "notify_result", "done", "notify_placement"]:
                last_log = ActionLog.objects.filter(profile=profile, action=action).order_by('-timestamp').first()
                if last_log:
                    action_log_times[action] = last_log.timestamp.strftime('%Y-%m-%d %H:%M')
                else:
                    action_log_times[action] = None
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
                'documents_by_group': grouped_documents,
                'documents': document_details,
                'is_completed': complete,
                'processed_by': processed_by,
                'approved_documents_count': approved_count,
                'missing_documents': missing_documents,
                'skills_passbook_result': skills_passbook_result,
                'experience_document_result': experience_document_result,
                'action_log_times': action_log_times,
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
    DOCUMENT_GROUP_ORDER = [
    "Experience",
    "Medical Requirements",
    "NACC Requirements",
    "Additional Facility Requirements",
    "Documents Required After Placement Completion"
]
    REQUIRED_DOCUMENTS = {
        "Medical Report Form",
        "Covid Vaccination Certificate",
        "Vulnerable Sector Check",
        "CPR & First Aid",
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
            docs_sorted = sorted(profile.documents.all(), key=lambda d: allowed_docs.index(d.document_type) if d.document_type in allowed_docs else 999)
            latest_approved_log = None
            approved_count = 0
            for doc in docs_sorted:
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
                    'uploaded_at': format_long_date(doc.uploaded_at) if doc.uploaded_at else '-',
                    'approval_logs': approver_actions
                })
            grouped_documents = OrderedDict((group, []) for group in self.DOCUMENT_GROUP_ORDER)
            # --- Custom logic for Medical Requirements group ---
            merged_medical_doc = None
            for doc in docs_sorted:
                if doc.document_type == 'Merged Medical Certificate':
                    merged_medical_doc = doc
                    break
            # Always build all groups except Medical Requirements first
            for doc in docs_sorted:
                group = document_group(doc.document_type)
                if not group or group == 'Medical Requirements':
                    continue
                latest_approval = ApprovalLog.objects.filter(document=doc, action="Approved").order_by('-timestamp').first()
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
                doc_info = {
                    'id': doc.id,
                    'status': doc.status,
                    'document_type': doc.document_type,
                    'file': doc.file.url if doc.file else None,
                    'rejection_reason': doc.rejection_reason,
                    'uploaded_at': format_long_date(doc.uploaded_at) if doc.uploaded_at else '-',
                    'updated_at': format_long_date(doc.updated_at) if doc.updated_at else '-',
                    'approved_at': format_long_date(doc.approved_at) if doc.approved_at else '-',
                    'rejected_at': format_long_date(doc.rejected_at) if doc.rejected_at else '-',
                    'uploaded_new_file': getattr(doc, 'uploaded_new_file', False),
                    'version': getattr(doc, 'version', 1),
                    'approval_logs': approver_actions
                }
                grouped_documents[group].append(doc_info)
            # Now handle Medical Requirements group
            if merged_medical_doc:
                group = document_group(merged_medical_doc.document_type)
                latest_approval = ApprovalLog.objects.filter(document=merged_medical_doc, action="Approved").order_by('-timestamp').first()
                approval_logs = ApprovalLog.objects.filter(document=merged_medical_doc)
                approver_actions = [
                    {
                        "approver": log.approver.full_name if log.approver else "Unknown",
                        "action": log.action,
                        "reason": log.reason,
                        "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    for log in approval_logs
                ]
                doc_info = {
                    'id': merged_medical_doc.id,
                    'status': merged_medical_doc.status,
                    'document_type': merged_medical_doc.document_type,
                    'file': merged_medical_doc.file.url if merged_medical_doc.file else None,
                    'rejection_reason': merged_medical_doc.rejection_reason,
                    'uploaded_at': format_long_date(merged_medical_doc.uploaded_at) if merged_medical_doc.uploaded_at else '-',
                    'updated_at': format_long_date(merged_medical_doc.updated_at) if merged_medical_doc.updated_at else '-',
                    'approved_at': format_long_date(merged_medical_doc.approved_at) if merged_medical_doc.approved_at else '-',
                    'rejected_at': format_long_date(merged_medical_doc.rejected_at) if merged_medical_doc.rejected_at else '-',
                    'uploaded_new_file': getattr(merged_medical_doc, 'uploaded_new_file', False),
                    'version': getattr(merged_medical_doc, 'version', 1),
                    'approval_logs': approver_actions
                }
                grouped_documents['Medical Requirements'] = [doc_info]
            else:
                # Only add individual medical docs if merged does not exist
                for doc in docs_sorted:
                    if document_group(doc.document_type) != 'Medical Requirements':
                        continue
                    latest_approval = ApprovalLog.objects.filter(document=doc, action="Approved").order_by('-timestamp').first()
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
                    doc_info = {
                        'id': doc.id,
                        'status': doc.status,
                        'document_type': doc.document_type,
                        'file': doc.file.url if doc.file else None,
                        'rejection_reason': doc.rejection_reason,
                        'uploaded_at': format_long_date(doc.uploaded_at) if doc.uploaded_at else '-',
                        'updated_at': format_long_date(doc.updated_at) if doc.updated_at else '-',
                        'approved_at': format_long_date(doc.approved_at) if doc.approved_at else '-',
                        'rejected_at': format_long_date(doc.rejected_at) if doc.rejected_at else '-',
                        'uploaded_new_file': getattr(doc, 'uploaded_new_file', False),
                        'version': getattr(doc, 'version', 1),
                        'approval_logs': approver_actions
                    }
                    grouped_documents['Medical Requirements'].append(doc_info)
            # --- Sort each group by allowed_docs order ---
            for group, docs in grouped_documents.items():
                grouped_documents[group] = sorted(
                    docs,
                    key=lambda d: allowed_docs.index(d['document_type']) if d['document_type'] in allowed_docs else 999
                )
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
            action_log_times = {}
            for action in ["remind_fee", "notify_result", "done", "notify_placement"]:
                last_log = ActionLog.objects.filter(profile=profile, action=action).order_by('-timestamp').first()
                if last_log:
                    action_log_times[action] = last_log.timestamp.strftime('%Y-%m-%d %H:%M')
                else:
                    action_log_times[action] = None

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
                'documents_by_group': grouped_documents,
                'is_completed': complete,
                'processed_by': processed_by,
                'approved_documents_count': approved_count,
                'action_log_times': action_log_times,
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

def send_skills_passbook_approved_email(profile):
    subject = "Book NACC Exam. Your Skills Passbook has been APPROVED!"
    try:
        student_id = profile.user.student_id_record.student_id
    except Exception:
        student_id = ""
    greeting_line = f"Dear {profile.first_name} {profile.last_name} with ID No. {student_id},"
    message = f"""
    <html>
    <body>
    <p>{greeting_line}</p>
    <p>Your Skills Passbook is now <span style='color:green; font-weight:bold;'>APPROVED</span>.</p>
    <p>To schedule your NACC Exam, please contact <a href='mailto:ara@peakcollege.ca'>ara@peakcollege.ca</a>.</p>
    <p>Remember to bring your Skills Passbook on the day of your exam.</p>
    <b>School Office Hours:</b>
    <ul>
      <li><b>Monday to Thursday:</b> 9:00 AM – 5:00 PM</li>
      <li><b>Saturday:</b> 9:30 AM – 4:00 PM</li>
    </ul>
    <p>Wishing you the best of luck on your NACC Exam Day, and thank you for completing your placement at Peak College!</p>
    <br>
    <p>Warm regards,<br>The Peak Healthcare Team</p>
    <p>Website: <a href='https://placement.peakcollege.ca/'>www.peakcollege.ca</a></p>
    <img src='http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg' width='240' height='90'/><br>
    1140 Sheppard Ave West<br>Unit #12, North York, ON<br>M3K 2A2
    </body>
    </html>
    """
    recipients = [profile.college_email, 'ara@peakcollege.ca']
    email = EmailMessage(subject, message, to=recipients)
    email.content_subtype = "html"
    email.send()

def send_skills_passbook_rejected_email(profile, rejection_reason, timestamp):
    subject = "Skills Passbook Rejected - Action Required"
    try:
        student_id = profile.user.student_id_record.student_id
    except Exception:
        student_id = ""
    greeting_line = f"Dear {profile.first_name} {profile.last_name} with ID No. {student_id},"
    message = f"""
    <html>
    <body>
    <p>{greeting_line}</p>
    <p>Your Skills Passbook was <span style='color:red; font-weight:bold;'>REJECTED</span> on {timestamp}.</p>
    <p><b>Reason:</b> {rejection_reason}</p>
    <p>Please review the feedback and resubmit your Skills Passbook for approval.</p>
    <br>
    <p>Warm regards,<br>The Peak Healthcare Team</p>
    <p>Website: <a href='https://placement.peakcollege.ca/'>www.peakcollege.ca</a></p>
    <img src='http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg' width='240' height='90'/><br>
    1140 Sheppard Ave West<br>Unit #12, North York, ON<br>M3K 2A2
    </body>
    </html>
    """
    recipients = [profile.college_email, 'ara@peakcollege.ca']
    email = EmailMessage(subject, message, to=recipients)
    email.content_subtype = "html"
    email.send()

@csrf_exempt
@user_passes_test(lambda u: u.is_superuser)
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
        # Set approval/rejection timestamps
        from django.utils import timezone
        if action == DocumentStatus.APPROVED.value:
            document.approved_at = timezone.now()
            document.rejected_at = None
        elif action == DocumentStatus.REJECTED.value:
            document.rejected_at = timezone.now()
            document.approved_at = None
        else:
            document.approved_at = None
            document.rejected_at = None
        document.save()

        approval_log = ApprovalLog.objects.create(
            approver=approver,
            document=document,
            action=action,
            reason=rejection_reason if action == DocumentStatus.REJECTED.value else None,
        )

        # If approved and document type is Experience Document, update required_hours
        if action == DocumentStatus.APPROVED.value and document.document_type == "Experience Document":
            document.profile.required_hours = 200
            document.profile.save()

        # If approved and document type is Skills Passbook, update stage to DONE and send email
        if action == DocumentStatus.APPROVED.value and document.document_type == "Skills Passbook":
            document.profile.stage = "DONE"
            document.profile.save()
            send_skills_passbook_approved_email(document.profile)

        # If rejected and document type is Skills Passbook, send rejection email with timestamp
        if action == DocumentStatus.REJECTED.value and document.document_type == "Skills Passbook":
            send_skills_passbook_rejected_email(document.profile, rejection_reason, approval_log.timestamp.strftime('%Y-%m-%d %H:%M:%S'))

        # Send placement notification
        message = f"Your document '{document.document_type}' has been {action.lower()}."
        if action == DocumentStatus.REJECTED.value:
            message += f" Reason: {rejection_reason}"

        PlacementNotification.objects.create(
            profile=document.profile,
            subject=f"Document {action}: {document.document_type}",
            message=message
        )

        # After approval, check if all medical requirements are approved and PDFs
        MEDICAL_REQUIREMENTS = [
            'Medical Report Form',
            'X-Ray Result',
            'MMR Lab/Vax Record',
            'Varicella Lab/Vax Record',
            'TDAP Vax Record',
            'Hepatitis A Lab/Vax Record',
            'Hepatitis B Lab/Vax Record',
        ]
        if document.document_type in MEDICAL_REQUIREMENTS and action == DocumentStatus.APPROVED.value:
            merge_medical_requirements_if_ready(document.profile, debug_prefix="[DEBUG]")

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
            <p><span class="highlight">Required Hours:</span> {requested_hours} Hours</p>

            <p><span class="highlight">Kindly observe the following during your placement:</span></p>
            <ul>
                <li>Be there at least 15 minutes prior to your scheduled time.</li>
                <li>Wear proper uniform and proper shoes.</li>
                <li>Display your Student ID or name tag.</li>
                <li>Facilities are scent-free; only use unscented products.</li>
                <li>Cell phones are not permitted during work hours.</li>
                <li>If you are feeling unwell, kindly follow the facility's policy.</li>
                <li>Bring your skills passbook to log your hours and have it evaluated at the end.</li>
            </ul>

            <p>Remember to follow the directives of your preceptor. If unclear, always ask.</p>

            <p><span class="highlight">Other important matters:</span></p>
            <ol>
                <li>Placement Key Points: <a href="#">Click here</a>.</li>
                <li>After your placement, scan and upload your timesheet and passbook here: <a href="#">Click here</a>.</li>
                <li>Reply to this email to confirm you've read and understood the contents.</li>
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
    subject = 'Placement Documents Needed – Action Required'

    # Build the dynamic list of rejected documents as bullets
    document_list_html = ""
    for doc in rejected_documents:
        reason = doc.rejection_reason if doc.rejection_reason else "No reason provided"
        document_list_html += f"<li>{doc.document_type} – {reason}</li>"

    # HTML Email message (revised as per new requirements)
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
            ul {{
                margin-top: 0.5em;
                margin-bottom: 1em;
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
            <p>Thank you for submitting your placement documents.</p>
            <p>Upon review, we found that some of the submitted documents do not meet the required standards for approval. Below are the specific reasons for rejection:</p>
            <p><b>Rejected Documents & Reasons:</b></p>
            <ul>
                {document_list_html}
            </ul>
            <p>To proceed, please log in to your profile and resubmit the corrected documents ensuring they meet all outlined requirements. The Placement Team will re-evaluate your submission once the updated documents are provided.</p>
            <p><a href="https://www.peakcollege.ca" class="highlight">Placement Link: Click here.</a></p>
            <p>We appreciate your prompt attention to this matter and look forward to your updated submission.</p>
            <div class="footer">
                <span>Warm regards,</span><br><br>
                <span>Peak HealthCare Private College</span><br>
                <span>Website: <a href="https://www.peakcollege.ca">www.peakcollege.ca</a></span><br>
                <br>
                <span>1140 Sheppard Ave W - Unit 12</span><br>
                <span>North York, ON</span><br>
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
<p>The Placement Coordinator: We will reach out to you through email or phone call. Once you finalize with her which facility you're going to do your placement, she will inform you of your Placement Orientation Date.</p>
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

        # --- Medical Requirements group as per forms_extras.py ---
        MEDICAL_REQUIREMENTS = [
            'Medical Report Form',
            'X-Ray Result',
            'MMR Lab/Vax Record',
            'Varicella Lab/Vax Record',
            'TDAP Vax Record',
            'Hepatitis A Lab/Vax Record',
            'Hepatitis B Lab/Vax Record',
        ]

        # Prepare a dict of approved documents by type
        approved_docs = {doc.document_type: doc for doc in documents if doc.status == 'Approved' and doc.file and doc.file.name}
        all_medical_approved = all(doc_type in approved_docs for doc_type in MEDICAL_REQUIREMENTS)
        merged_medical_pdf_path = None
        merged_medical_pdf_name = None
        if all_medical_approved:
            # Merge all medical requirement PDFs
            pdf_paths = [approved_docs[doc_type].file.path for doc_type in MEDICAL_REQUIREMENTS]
            safe_first_name = re.sub(r'\W+', '_', profile.first_name or '').strip('_')
            safe_last_name = re.sub(r'\W+', '_', profile.last_name or '').strip('_')
            merged_medical_pdf_name = f"{safe_first_name}_{safe_last_name}_MedCert.pdf"
            merged_medical_pdf_dir = os.path.join(settings.MEDIA_ROOT, "documents", "uploads")
            os.makedirs(merged_medical_pdf_dir, exist_ok=True)
            merged_medical_pdf_path = os.path.join(merged_medical_pdf_dir, merged_medical_pdf_name)
            merge_pdfs(pdf_paths, merged_medical_pdf_path)

        if action == 'notify_result':
            zip_file_name = f"{profile.id}_{profile.first_name}_{profile.last_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            zip_file_path = os.path.join(settings.MEDIA_ROOT, 'documents', 'uploads', zip_file_name)

            with zipfile.ZipFile(zip_file_path, 'w') as zipf:
                for document in documents:
                    if document.file and document.file.name: 
                        # Exclude individual medical requirement files if merged PDF is present
                        if all_medical_approved and document.document_type in MEDICAL_REQUIREMENTS:
                            continue
                        try:
                            zipf.write(document.file.path, os.path.basename(document.file.name))
                        except Exception as e:
                            continue  
                # Add merged medical PDF if present
                if all_medical_approved and merged_medical_pdf_path:
                    zipf.write(merged_medical_pdf_path, merged_medical_pdf_name)
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
                        # Exclude individual medical requirement files if merged PDF is present
                        if all_medical_approved and document.document_type in MEDICAL_REQUIREMENTS:
                            continue
                        try:
                            zipf.write(document.file.path, os.path.basename(document.file.name))
                        except Exception:
                            continue
                # Add merged medical PDF if present
                if all_medical_approved and merged_medical_pdf_path:
                    zipf.write(merged_medical_pdf_path, merged_medical_pdf_name)
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

        # Log the action
        try:
            student_id = profile.user.student_id_record.student_id
        except Exception:
            student_id = ''
        # Only create log if it does not already exist for this profile/action
        if not ActionLog.objects.filter(profile=profile, action=action).exists():
            ActionLog.objects.create(
                student_id=student_id,
                profile=profile,
                action=action,
                performed_by=request.user if request.user.is_authenticated else None
            )

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

        # Mark the old document as not a new upload
        existing_document.uploaded_new_file = False
        existing_document.save()
        # Set the new version number
        new_version = existing_document.version + 1
        new_document = Document.objects.create(
            profile=profile,
            document_type=document_type,
            file=saved_path,
            file_name=new_file_name,
            status="In Review",
            uploaded_new_file=True,
            version=new_version
        )

        # Notify the latest rejecting approver if the previous document was rejected
        latest_rejection = ApprovalLog.objects.filter(document=existing_document, action="Rejected").order_by('-timestamp').first()
        if latest_rejection and latest_rejection.approver and latest_rejection.approver.user.email:
            approver_email = latest_rejection.approver.user.email
            subject = f"Resubmission: {document_type} by {profile.first_name} {profile.last_name}"
            review_link = f"https://www.peakcollege.ca/approver-view?document_id={new_document.id}"
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
                <div class=\"container\">
                    <p>Dear {latest_rejection.approver.full_name},</p>
                    <p>The student <strong>{profile.first_name} {profile.last_name}</strong> has resubmitted the <strong>{document_type}</strong> document for your review.</p>
                    <p>Please click the link below to review and take action:</p>
                    <p><a href=\"{review_link}\" class=\"highlight\">Review Document: Click here</a></p>
                    <div class=\"footer\">
                        <p>Best of luck with your placement process and thanks again for completing your Placement at Peak College!</p>
                        <span>Warm regards, </span>
                        <br>
                        <span> The Peak Healthcare Team</span>
                        <br>
                        <span>Website: <a href=\"https://www.peakcollege.ca\">www.peakcollege.ca</a></span>
                        <br>
                        <img src=\"http://peakcollege.ca/wp-content/uploads/2015/06/PEAK-Logo-Black-Green.jpg\"></img>
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
            from django.core.mail import send_mail
            send_mail(
                subject,
                "",  # Plain text fallback
                settings.DEFAULT_FROM_EMAIL,
                [approver_email],
                html_message=message,
            )

        existing_document.delete()
        
        try:
            student_id = profile.user.student_id_record.student_id
        except StudentID.DoesNotExist:
            student_id = None 
        if document_type == "Resume":
            send_email_notify_resume(profile, [new_document], student_id=student_id)
        elif document_type == "Skills Passbook":
            send_email_notify_skills_passbook(profile, [new_document], student_id=student_id)

        # After uploading a new file, check for medical requirements
        MEDICAL_REQUIREMENTS = [
            'Medical Report Form',
            'X-Ray Result',
            'MMR Lab/Vax Record',
            'Varicella Lab/Vax Record',
            'TDAP Vax Record',
            'Hepatitis A Lab/Vax Record',
            'Hepatitis B Lab/Vax Record',
        ]
        medical_docs = Document.objects.filter(profile=profile, document_type__in=MEDICAL_REQUIREMENTS)
        if medical_docs.count() == len(MEDICAL_REQUIREMENTS) and all(doc.file and doc.file.name.lower().endswith('.pdf') for doc in medical_docs):
            pdf_paths = [doc.file.path for doc in medical_docs]
            safe_first_name = re.sub(r'\W+', '_', profile.first_name or '').strip('_')
            safe_last_name = re.sub(r'\W+', '_', profile.last_name or '').strip('_')
            merged_medical_pdf_name = f"{safe_first_name}_{safe_last_name}_MedCert.pdf"
            merged_medical_pdf_dir = os.path.join(settings.MEDIA_ROOT, "documents", "uploads")
            os.makedirs(merged_medical_pdf_dir, exist_ok=True)
            merged_medical_pdf_path = os.path.join(merged_medical_pdf_dir, merged_medical_pdf_name)
            merge_pdfs(pdf_paths, merged_medical_pdf_path)
            with open(merged_medical_pdf_path, 'rb') as f:
                merged_file_content = ContentFile(f.read())
                merged_file_storage_path = default_storage.save(os.path.join("documents/uploads", merged_medical_pdf_name), merged_file_content)
            Document.objects.update_or_create(
                profile=profile,
                document_type='Merged Medical Certificate',
                defaults={
                    'file': merged_file_storage_path,
                    'file_name': merged_medical_pdf_name,
                    'status': 'In Review',
                }
            )

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
            "Medical Report Form",
            "Covid Vaccination Certificate",
            "Vulnerable Sector Check",
            "CPR & First Aid",
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
            "Medical Report Form",
            "Covid Vaccination Certificate",
            "Vulnerable Sector Check",
            "CPR & First Aid",
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
        # Get distinct provinces
        provinces = list(set(Facility.objects.values_list('province', flat=True)))

        # Pass city objects with name and province
        from .models import City
        cities = list(City.objects.values('name', 'province'))
        # Sort: Ontario cities first, then others
        cities = sorted(cities, key=lambda c: (c['province'] != 'Ontario', c['province'], c['name']))
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


def get_profiles_facilities_orientations(request=None):
    from .models import StudentID
    required_docs = [
        "Medical Report Form",
        "Covid Vaccination Certificate",
        "Vulnerable Sector Check",
        "Mask Fit Certificate",
        "CPR & First Aid",
        "Experience Document",  # Always required and must be approved
    ]

    profiles_qs = PlacementProfile.objects.select_related(
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

    # Filtering
    assigned_facility_id = None
    status = None
    orientation_date_id = None
    search_query = None
    if request:
        assigned_facility_id = request.GET.get('assigned_facility', '')
        status = request.GET.get('status', '')
        orientation_date_id = request.GET.get('orientation_date', '')
        search_query = request.GET.get('search', '').strip()
        if assigned_facility_id:
            profiles_qs = profiles_qs.filter(assigned_facility__id=assigned_facility_id)
        if status:
            profiles_qs = profiles_qs.filter(stage=status)
        if orientation_date_id:
            profiles_qs = profiles_qs.filter(orientation_date__id=orientation_date_id)
        if search_query:
            profiles_qs = profiles_qs.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(user__student_id_record__student_id__icontains=search_query)
            )

    # Fetch facilities and orientation dates
    facilities = Facility.objects.filter(status='Active').order_by('name')
    orientation_dates = OrientationDate.objects.order_by('-orientation_date')
    status_choices = [s[0] for s in PlacementProfile._meta.get_field('stage').choices if s[0]]

    # Prepare profiles with student_id and start/end dates
    profiles = []
    for profile in profiles_qs:
        try:
            student_id = profile.user.student_id_record.student_id
        except Exception:
            student_id = ''
        profiles.append({
            'id': profile.id,
            'user': profile.user,
            'first_name': profile.first_name,
            'last_name': profile.last_name,
            'college_email': profile.college_email,
            'experience_level': profile.experience_level,
            'assigned_facility': profile.assigned_facility,
            'orientation_date': profile.orientation_date,
            'official_start_date': profile.official_start_date,
            'exact_placement_end_date': profile.exact_placement_end_date,
            'stage': profile.stage,
            'student_id': student_id,
        })

    return {
        "profiles": profiles,
        "facilities": facilities,
        "orientation_dates": orientation_dates,
        "status_choices": status_choices,
        "selected_facility": assigned_facility_id or '',
        "selected_status": status or '',
        "selected_orientation_date": orientation_date_id or '',
    }

def assign_facility_and_orientation_date_to_users(request):
    context = get_profiles_facilities_orientations(request)
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
            # Set stage to IN_PLACEMENT if both facility and orientation are assigned and stage is ONGOING_PROCESS
            for profile in profiles:
                if profile.stage == 'ONGOING_PROCESS' and profile.assigned_facility and profile.orientation_date:
                    profile.stage = 'IN_PLACEMENT'
                    profile.save(update_fields=['stage'])

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
        
        # Ontario first, then others alphabetically
        ordered_city_data = {}
        if 'Ontario' in city_data:
            ordered_city_data['Ontario'] = sorted(city_data['Ontario'])
        for prov in sorted(city_data.keys()):
            if prov != 'Ontario':
                ordered_city_data[prov] = sorted(city_data[prov])
        
        # Return the data as JSON
        return JsonResponse(ordered_city_data)
    
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

            profile = PlacementProfile.objects.get(id=profile_id)
            updated = False
            if start_date:
                profile.official_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
                updated = True
            if end_date:
                profile.exact_placement_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
                updated = True
            if updated:
                profile.save()
                return JsonResponse({"status": "success", "message": "Start date and/or end date updated successfully."})
            else:
                return JsonResponse({"status": "error", "message": "No valid date provided."})

        except PlacementProfile.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Profile not found."})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})
    return JsonResponse({"status": "error", "message": "Invalid request."})

def set_module_completed_view(request, profile_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            module_completed_value = data.get("module_completed")
            profile = PlacementProfile.objects.get(id=profile_id)
            profile.module_completed = module_completed_value
            profile.save()
            return JsonResponse({"status": "success", "message": "Modules completed updated successfully."})
        except PlacementProfile.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Profile not found."})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})
    return JsonResponse({"status": "error", "message": "Invalid request."})

def pregnancy_policy_view(request):
    return render(request, "pregnancy_policy.html")

def get_student_profile_by_id(request, profile_id):
    DOCUMENT_GROUP_ORDER = [
    "Experience",
    "Medical Requirements",
    "NACC Requirements",
    "Additional Facility Requirements",
    "Documents Required After Placement Completion"
]
    profile = get_object_or_404(
        PlacementProfile.objects.select_related('assigned_facility', 'orientation_date')
        .prefetch_related('documents'),
        id=profile_id
    )

    REQUIRED_DOCUMENTS = {
        "Medical Report Form",
        "Covid Vaccination Certificate",
        "Vulnerable Sector Check",
        "CPR & First Aid",
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

    # Add missing_documents calculation
    missing_documents = []
    for doc_type in REQUIRED_DOCUMENTS:
        doc = documents.get(doc_type)
        if not doc or not doc.file_name:
            missing_documents.append(doc_type)

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
            'uploaded_at': format_long_date(doc.uploaded_at) if doc.uploaded_at else '-',
            'approval_logs': approver_actions
        })
    
        grouped_documents = OrderedDict((group, []) for group in DOCUMENT_GROUP_ORDER)
        for doc in profile.documents.all():
            group = document_group(doc.document_type)
            if not group:
                continue  # Skip documents not in any known group
            
            latest_approval = ApprovalLog.objects.filter(document=doc, action="Approved").order_by('-timestamp').first()
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

            doc_info = {
                'id': doc.id,
                'status': doc.status,
                'document_type': doc.document_type,
                'file': doc.file.url if doc.file else None,
                'rejection_reason': doc.rejection_reason,
                'uploaded_at': format_long_date(doc.uploaded_at) if doc.uploaded_at else '-',
                'updated_at': format_long_date(doc.updated_at) if doc.updated_at else '-',
                'approved_at': format_long_date(doc.approved_at) if doc.approved_at else '-',
                'rejected_at': format_long_date(doc.rejected_at) if doc.rejected_at else '-',
                'uploaded_new_file': getattr(doc, 'uploaded_new_file', False),
                'version': getattr(doc, 'version', 1),
                'approval_logs': approver_actions
            }

            grouped_documents[group].append(doc_info)
    try:
        student_id = profile.user.student_id_record.student_id
    except StudentID.DoesNotExist:
        student_id = ''

    context = {
        'profile': profile,
        'student_id': student_id,
        'documents': document_details,
        'is_completed': complete,
        'documents_by_group': grouped_documents,
        'missing_documents': missing_documents,  # <-- Add this line
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
    show_under_review_popup = request.session.pop('show_under_review_popup', False)
    context = {
        'has_profile': has_profile,
        'show_under_review_popup': show_under_review_popup,
    }
    return render(request, 'base.html', context)

@method_decorator(user_passes_test(lambda u: u.is_superuser), name='dispatch')
class SkillsPassbookListView(View):
    def get(self, request):
        from .models import Document, PlacementProfile, ApprovalLog
        from django.db.models import Q

        # Filters
        status_filter = request.GET.get('status', '')
        search_query = request.GET.get('search', '').strip().lower()

        # Get all Skills Passbook documents that have been uploaded
        skills_docs = Document.objects.filter(document_type='Skills Passbook').select_related('profile__user')
        if status_filter:
            skills_docs = skills_docs.filter(status=status_filter)
        # Only show documents that have a file uploaded
        skills_docs = skills_docs.exclude(file_name__isnull=True).exclude(file_name='')

        # Search by student name, email, or student ID
        if search_query:
            skills_docs = skills_docs.filter(
                Q(profile__first_name__icontains=search_query) |
                Q(profile__last_name__icontains=search_query) |
                Q(profile__college_email__icontains=search_query) |
                Q(profile__user__student_id_record__student_id__icontains=search_query)
            )

        # Prepare data for template
        skills_data = []
        for doc in skills_docs:
            profile = doc.profile
            try:
                student_id = profile.user.student_id_record.student_id
            except Exception:
                student_id = ''
            latest_approval = ApprovalLog.objects.filter(document=doc).order_by('-timestamp').first()
            latest_comment = ApprovalLog.objects.filter(document=doc, action='Comment').order_by('-timestamp').first()
            skills_data.append({
                'doc_id': doc.id,
                'profile_id': profile.id,
                'student_id': student_id,
                'first_name': profile.first_name,
                'last_name': profile.last_name,
                'email': profile.college_email,
                'status': doc.status,
                'file_url': doc.file.url if doc.file else '',
                'uploaded_at': doc.uploaded_at,
                'rejection_reason': doc.rejection_reason,
                'latest_approval': latest_approval,
                'latest_comment': latest_comment.reason if latest_comment else '',
            })

        # For filter dropdown
        status_choices = ['In Review', 'Approved', 'Rejected']

        return render(request, 'skills_passbook_list.html', {
            'skills_data': skills_data,
            'status_choices': status_choices,
            'selected_status': status_filter,
            'search_query': search_query,
        })

@csrf_exempt
@user_passes_test(lambda u: u.is_superuser)
def ready_for_exam(request, profile_id):
    if request.method == 'POST':
        from .models import PlacementProfile
        profile = get_object_or_404(PlacementProfile, id=profile_id)
        profile.stage = 'READY'
        profile.save()
        return JsonResponse({'message': 'Marked as Ready For Exam!'}, status=200)
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
@user_passes_test(lambda u: u.is_superuser)
def add_document_comment(request, document_id):
    if request.method == 'POST':
        from .models import Document, ApprovalLog, Approver
        document = get_object_or_404(Document, id=document_id)
        approver = get_object_or_404(Approver, user=request.user)
        comment = request.POST.get('comment', '').strip()
        if not comment:
            return JsonResponse({'error': 'Comment cannot be empty.'}, status=400)
        ApprovalLog.objects.create(
            approver=approver,
            document=document,
            action='Comment',
            reason=comment,
        )
        return JsonResponse({'message': 'Comment added!'}, status=200)
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
@login_required
@require_POST
def update_pregnancy_signature(request):
    user = request.user
    from .models import StudentID
    # Try to get or create the StudentID object
    student_id_obj, created = StudentID.objects.get_or_create(
        user=user,
        defaults={
            'student_id': f"{user.username}_{int(time.time())}"
        }
    )
    file = request.FILES.get('pregnancy_signature_file')
    signed_on_date = request.POST.get('signed_on_date')
    errors = {}
    if not file:
        errors['pregnancy_signature_file'] = 'Signature file is required.'
    elif not file.content_type.startswith('image/'):
        errors['pregnancy_signature_file'] = 'Only image files are allowed.'
    elif file.size > 2 * 1024 * 1024:
        errors['pregnancy_signature_file'] = 'File size must be 2MB or less.'
    if not signed_on_date:
        errors['signed_on_date'] = 'Date is required.'
    if errors:
        return JsonResponse({'success': False, 'errors': errors}, status=400)
    student_id_obj.pregnancy_signature_file = file
    student_id_obj.signed_on_date = signed_on_date
    student_id_obj.save()
    return JsonResponse({'success': True})
@require_GET
def get_action_logs(request, profile_id):
    profile = get_object_or_404(PlacementProfile, id=profile_id)
    logs = ActionLog.objects.filter(profile=profile).order_by('-timestamp')
    data = [
        {
            'action': log.get_action_display(),
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'performed_by': log.performed_by.get_full_name() if log.performed_by else 'System',
            'extra_info': log.extra_info or ''
        }
        for log in logs
    ]
    return JsonResponse({'logs': data})

def merge_pdfs(pdf_paths, output_path):
    """
    Merge multiple PDF files into a single PDF.
    Args:
        pdf_paths (list): List of file paths to PDF files.
        output_path (str): Output file path for the merged PDF.
    """
    merger = PdfMerger()
    for pdf in pdf_paths:
        merger.append(pdf)
    with open(output_path, 'wb') as fout:
        merger.write(fout)
    merger.close()

# --- Helper function for merging medical requirements ---
def merge_medical_requirements_if_ready(profile, debug_prefix="[DEBUG]"):
    MEDICAL_REQUIREMENTS = [
        'Medical Report Form',
        'X-Ray Result',
        'MMR Lab/Vax Record',
        'Varicella Lab/Vax Record',
        'TDAP Vax Record',
        'Hepatitis A Lab/Vax Record',
        'Hepatitis B Lab/Vax Record',
    ]
    approved_medical_docs = Document.objects.filter(
        profile=profile,
        document_type__in=MEDICAL_REQUIREMENTS,
        status=DocumentStatus.APPROVED.value
    )
    print(f"{debug_prefix} Approved medical docs count: {approved_medical_docs.count()} / {len(MEDICAL_REQUIREMENTS)}")
    if approved_medical_docs.count() == len(MEDICAL_REQUIREMENTS) and all(doc.file and doc.file.name.lower().endswith('.pdf') for doc in approved_medical_docs):
        print(f"{debug_prefix} All medical docs approved and are PDFs. Proceeding to merge.")
        pdf_paths = [doc.file.path for doc in approved_medical_docs]
        safe_first_name = re.sub(r'\\W+', '_', profile.first_name or '').strip('_')
        safe_last_name = re.sub(r'\\W+', '_', profile.last_name or '').strip('_')
        merged_medical_pdf_name = f"{safe_first_name}_{safe_last_name}_MedCert.pdf"
        merged_medical_pdf_dir = os.path.join(settings.MEDIA_ROOT, "documents", "uploads")
        os.makedirs(merged_medical_pdf_dir, exist_ok=True)
        merged_medical_pdf_path = os.path.join(merged_medical_pdf_dir, merged_medical_pdf_name)
        merge_pdfs(pdf_paths, merged_medical_pdf_path)
        print(f"{debug_prefix} Merged PDF created at {merged_medical_pdf_path}")
        with open(merged_medical_pdf_path, 'rb') as f:
            merged_file_content = ContentFile(f.read())
            merged_file_storage_path = default_storage.save(os.path.join("documents/uploads", merged_medical_pdf_name), merged_file_content)
        doc_obj, created = Document.objects.update_or_create(
            profile=profile,
            document_type='Merged Medical Certificate',
            defaults={
                'file': merged_file_storage_path,
                'file_name': merged_medical_pdf_name,
                'status': 'Approved',
            }
        )
        print(f"{debug_prefix} Merged Medical Certificate Document {'created' if created else 'updated'}: {doc_obj.id}")
    else:
        print(f"{debug_prefix} Not all medical docs are approved and PDFs. No merge performed.")

@csrf_exempt
@require_POST
def edit_orientation_date(request, pk):
    from .models import OrientationDate
    import json
    try:
        orientation = OrientationDate.objects.get(pk=pk)
        new_date = request.POST.get('orientation_date')
        if not new_date:
            return JsonResponse({'success': False, 'error': 'No date provided.'})
        orientation.orientation_date = new_date
        orientation.save()
        return JsonResponse({'success': True})
    except OrientationDate.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Orientation date not found.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
