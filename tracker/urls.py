from django.urls import path, include
from . import views
from django.contrib.auth import views as auth_views
from django.contrib import admin
urlpatterns = [
    path('', views.index, name='index1'),
    path('accounts/', include('django.contrib.auth.urls')),
]