from django.apps import AppConfig


class UserSectionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user_section'
    def ready(self):
        import user_section.signals  # 👈 this line ensures signals are loaded

