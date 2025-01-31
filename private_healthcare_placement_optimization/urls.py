from django.contrib.auth.decorators import login_required
from django.urls import path
from .views import (
    PlacementProfileView, DocumentView, ApproverView, 
    ApprovalLogView, FeeStatusView, PlacementNotificationView, profile_submission_success
)
from django.contrib.auth import views as auth_views
from .views import *

urlpatterns = [
    path('create-placement-profile/', login_required(PlacementProfileView.as_view()), name='create_placement_profile'),
    path('documents/<int:profile_id>/', login_required(DocumentView.as_view()), name='documents'),
    path('approvers/', login_required(ApproverView.as_view()), name='approvers'),
    path('approval-logs/', login_required(ApprovalLogView.as_view()), name='approval_logs'),
    path('fee-status/', login_required(FeeStatusView.as_view()), name='fee_status'),
    path('notifications/', login_required(PlacementNotificationView.as_view()), name='notifications'),
    path('profile_submission_success/', profile_submission_success, name='profile_submission_success'),
    path('login/', StudentLoginView.as_view(), name='login'),
    path('', StudentProfileLogsView.as_view(), name='student_profile_logs'),
    path('signup/', signup, name='signup'),
    path('staff-signup/', StaffSignupView.as_view(), name='staff_signup'),
    path('profile/', profile_view, name='profile'),  # Profile page
    path('logout/', logout_view, name='logout'),
]
