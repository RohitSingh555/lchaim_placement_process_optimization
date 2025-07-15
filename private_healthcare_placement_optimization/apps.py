from django.apps import AppConfig


class LchaimPlacementProcessOptimizationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'private_healthcare_placement_optimization'

    def ready(self):
        from apscheduler.schedulers.background import BackgroundScheduler
        from private_healthcare_placement_optimization.scheduled_tasks import send_rejected_document_reminders
        import atexit
        scheduler = BackgroundScheduler()
        scheduler.add_job(send_rejected_document_reminders, 'cron', hour=0, minute=0)  # Every day at 12am
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())
