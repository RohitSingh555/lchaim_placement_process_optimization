from django.contrib.auth.decorators import login_required
from django.urls import path
from .views import (
    PlacementProfileView, DocumentView, ApproverView, profile_submission_success
)
from django.contrib.auth import views as auth_views
from .views import *
from .views import edit_orientation_date
from .views import admin_dashboard
from .views import reminders_page_view

urlpatterns = [
    path('create-placement-profile/', login_required(PlacementProfileView.as_view()), name='create_placement_profile'),
    path('documents/<int:profile_id>/', login_required(DocumentView.as_view()), name='documents'),
    path('approvers/', login_required(ApproverView.as_view()), name='approvers'),
    path('profile_submission_success/', profile_submission_success, name='profile_submission_success'),
    path('login/', StudentLoginView.as_view(), name='login'),
    path('', StudentProfileLogsView.as_view(), name='student_profile_logs'),
    path('signup/', signup, name='signup'),
    path('staff-signup/', StaffSignupView.as_view(), name='staff_signup'),
    path('profile/', profile_view, name='profile'),  
    path("approve-document/<int:document_id>/", approve_document, name="approve_document"),
    path('logout/', logout_view, name='logout'),
    path('send-email/<int:profile_id>/<str:action>/', handle_button_action, name='send_email'),
    path('approvers-view/', approvers_view, name='approvers_view'),
    path('promote-to-approver/<int:user_id>/', promote_to_approver, name='promote_to_approver'),
    path('remove-from-approver/<int:user_id>/', remove_from_approver, name='remove_from_approver'),
    path("submit-new-file/", submit_new_file, name="submit_new_file"),
    path('validate-password/', validate_password, name='validate-password'),
    path("404/", custom_404, name="custom_404"),
    path('delete-profile/<int:profile_id>/', delete_profile, name='delete_profile'),
    path('profile/', profile_view, name='profile'),
    path("password-reset/", password_reset_request, name="password_reset"),
    path("password-reset/done/", password_reset_complete, name="password_reset_done"),
    path("reset/<uidb64>/<token>/", password_reset_confirm, name="password_reset_confirm"),
    path("send-documents-email/", SendDocumentsEmailView.as_view(), name="send_documents_email"),
    path('incomplete-profiles/', StudentIncompleteProfileLogsView.as_view(), name='incomplete_profiles'),
    path('complete-profiles/', complete_profiles_view, name='complete_profiles'),
    path('pending-users/', get_users_without_profiles_view, name='pending_users'),
    #path to delete user 
    path('delete-user/<int:user_id>/', delete_user, name='delete_user'),
    
     # Facility URLs
    path('facilities/', FacilityListView.as_view(), name='facility_list'),
    path('facilities/add/', FacilityCreateView.as_view(), name='facility_add'),
    path('facilities/<int:pk>/update/', update_facility, name='update_facility'),
    path('facilities/<int:pk>/delete/', FacilityDeleteView.as_view(), name='facility_delete'),
    path('facilities/<int:facility_id>/edit/', edit_facility, name='facility_edit'),
    path('set-official-start-date/<int:profile_id>/', set_official_start_date_view, name='set_official_start_date'),
    path('set-module-completed/<int:profile_id>/', set_module_completed_view, name='set_module_completed'),


    # OrientationDate URLs
    path('orientations/', OrientationDateListView.as_view(), name='orientation_list'),
    path('orientations/add/', OrientationDateCreateView.as_view(), name='orientation_add'),
    path('orientations/<int:pk>/edit/', edit_orientation_date, name='orientation_edit'),
    path('orientations/<int:pk>/delete/', OrientationDateDeleteView.as_view(), name='orientation_delete'),
    
    path('facilities/assign/', assign_facility_and_orientation_date_to_users, name='assign_facility_and_orientation_date_to_users'),
    path('assign-facility/', assign_facility_view, name='assign_facility'),
    path('cities-and-provinces/', get_cities_and_provinces, name='cities_and_provinces'),
    path("pregnancy-policy/", pregnancy_policy_view, name="pregnancy_policy"),
    path('student-profile/<int:profile_id>/', get_student_profile_by_id, name='get_student_profile_by_id'),
    path('update-stage/', update_stage, name='update-stage'),
    path('skills-passbook/', SkillsPassbookListView.as_view(), name='skills_passbook_list'),
    path('ready-for-exam/<int:profile_id>/', ready_for_exam, name='ready_for_exam'),
    path('add-document-comment/<int:document_id>/', add_document_comment, name='add_document_comment'),
    path('update-pregnancy-signature/', update_pregnancy_signature, name='update_pregnancy_signature'),
    path('get-action-logs/<int:profile_id>/', get_action_logs, name='get_action_logs'),
    path('dashboard/', admin_dashboard, name='admin_dashboard'),
    path('reminders/', reminders_page_view, name='reminders_page'),

]
handler404 = 'private_healthcare_placement_optimization.custom_404'