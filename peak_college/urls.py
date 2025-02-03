from django.contrib import admin
from django.urls import include, path
from peak_college import settings
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.conf.urls.static import static

# Create schema view for Swagger
schema_view = get_schema_view(
    openapi.Info(
        title="Lchaim Placement API",
        default_version='v1',
        description="API documentation for the Lchaim Placement Process Optimization",
        terms_of_service="https://www.peakcollege.ca/terms/",
        contact=openapi.Contact(email="support@peakcollege.ca"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('private_healthcare_placement_optimization.urls')),  
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='redoc-ui'),
]
