from django.contrib import admin
from .models import PlacementProfile, Document, Approver, ApprovalLog, FeeStatus, PlacementNotification

class PlacementProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'college_email', 'first_name', 'last_name', 
        'apt_house_no', 'street', 'city', 'province', 'postal_code', 
        'open_to_outside_city', 'experience_level', 'shift_requested', 'created_at'
    )
    search_fields = ('user__username', 'college_email', 'first_name', 'last_name', 'city', 'province')
    list_filter = ('experience_level', 'shift_requested', 'city', 'province', 'open_to_outside_city')
    readonly_fields = ('created_at',)


class DocumentAdmin(admin.ModelAdmin):
    list_display = ('profile', 'document_type', 'status', 'uploaded_at', 'rejection_reason')
    search_fields = ('profile__user__username', 'document_type', 'status')
    list_filter = ('status', 'document_type')
    readonly_fields = ('uploaded_at',)

class ApproverAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'position')
    search_fields = ('user__username', 'full_name', 'position')

class ApprovalLogAdmin(admin.ModelAdmin):
    list_display = ('approver', 'document', 'action', 'timestamp', 'reason')
    search_fields = ('approver__full_name', 'document__document_type', 'action')
    list_filter = ('action', 'timestamp')

class FeeStatusAdmin(admin.ModelAdmin):
    list_display = ('profile', 'is_paid', 'payment_due_date', 'last_reminder_sent', 'reminder_count')
    search_fields = ('profile__user__username',)
    list_filter = ('is_paid',)

class PlacementNotificationAdmin(admin.ModelAdmin):
    list_display = ('profile', 'subject', 'sent_at')
    search_fields = ('profile__user__username', 'subject')
    list_filter = ('sent_at',)

# Register the models
admin.site.register(PlacementProfile, PlacementProfileAdmin)
admin.site.register(Document, DocumentAdmin)
admin.site.register(Approver, ApproverAdmin)
admin.site.register(ApprovalLog, ApprovalLogAdmin)
admin.site.register(FeeStatus, FeeStatusAdmin)
admin.site.register(PlacementNotification, PlacementNotificationAdmin)
