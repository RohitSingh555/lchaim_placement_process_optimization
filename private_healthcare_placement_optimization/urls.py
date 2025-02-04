from django.contrib.auth.decorators import login_required
from django.urls import path
from .views import (
    PlacementProfileView, DocumentView, ApproverView, profile_submission_success
)
from django.contrib.auth import views as auth_views
from .views import *

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
]
