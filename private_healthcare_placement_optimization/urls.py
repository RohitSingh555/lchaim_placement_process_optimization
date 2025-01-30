from django import views
from django.urls import path
from .views import (
    PlacementProfileView, DocumentView, ApproverView, 
    ApprovalLogView, FeeStatusView, PlacementNotificationView
)
from . import views

urlpatterns = [
    path('create-placement-profile/', PlacementProfileView.as_view(), name='create_placement_profile'),
    path('documents/<int:profile_id>/', DocumentView.as_view(), name='documents'),
    path('approvers/', ApproverView.as_view(), name='approvers'),
    path('approval-logs/', ApprovalLogView.as_view(), name='approval_logs'),
    path('fee-status/', FeeStatusView.as_view(), name='fee_status'),
    path('notifications/', PlacementNotificationView.as_view(), name='notifications'),
    path('profile_submission_success/', views.profile_submission_success, name='profile_submission_success'),
]
