from django.utils import timezone
from datetime import timedelta
from private_healthcare_placement_optimization.models import Document, EmailReminderLog
from django.core.mail import send_mail
from django.conf import settings

def send_rejected_document_reminders():
    from private_healthcare_placement_optimization.models import PlacementProfile
    two_weeks_ago = timezone.now() - timedelta(days=14)
    rejected_docs = Document.objects.filter(
        status='Rejected',
        rejected_at__lte=two_weeks_ago
    ).select_related('profile')

    for doc in rejected_docs:
        profile = doc.profile
        # Check if a reminder was sent in the last 14 days for this document
        recent_log = EmailReminderLog.objects.filter(
            profile=profile,
            document=doc,
            email_type='rejected_reminder',
            sent_at__gte=timezone.now() - timedelta(days=14)
        ).exists()
        if recent_log:
            continue  # Skip if already sent in the last 2 weeks
        subject = "Reminder: Resubmit Your Placement Document"
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
                <p>Greetings {profile.first_name},</p>
                <p>This is a reminder that your document <b>{doc.document_type}</b> was <span style=\"color:red;font-weight:bold;\">REJECTED</span> over 2 weeks ago.</p>
                <p>Please log in to your placement portal and resubmit the corrected document as soon as possible to avoid delays in your placement process.</p>
                <p>
                    <a href=\"https://placement.peakcollege.ca/\" class=\"highlight\">Go to Placement Portal</a>
                </p>
                <div class=\"footer\">
                    <p>Best of luck with your placement process and thanks again for completing your Placement at Peak College!</p>
                    <span>Warm regards, </span>
                    <br>
                    <span> The Peak Healthcare Team</span>
                    <br>
                    <span>Website: <a href=\"https://placement.peakcollege.ca/\">www.peakcollege.ca</a></span>
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
        send_mail(
            subject,
            "",  # Plain text fallback
            settings.DEFAULT_FROM_EMAIL,
            [profile.college_email],
            html_message=message,
        )
        # Log the sent email
        EmailReminderLog.objects.create(
            profile=profile,
            document=doc,
            email_type='rejected_reminder'
        ) 