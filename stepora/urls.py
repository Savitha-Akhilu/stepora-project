"""
URL configuration for stepora project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from user_section import views
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    path('admin/', admin.site.urls),
    path('adminpanel/', include('adminpanel.urls')),
    path('', include('user_section.urls')),
    # path('accounts/', include('allauth.urls')),    #  handles google login URLs
    path('users/accounts/', include('allauth.urls')),  # User Google login
    path('redirect-after-login/', views.redirect_after_login, name='redirect_after_login'),
    path('adminpanel/products/', include(('products.urls', 'products'), namespace='products')),
    path('cart/', include('cart.urls')),


]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

