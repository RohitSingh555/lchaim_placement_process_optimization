from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from .models import PlacementProfile, Document, Approver, ApprovalLog, FeeStatus, PlacementNotification
from .forms import PlacementProfileForm, DocumentForm  # assuming you created the forms
from django.core.mail import send_mail
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator

from django.db import transaction

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
