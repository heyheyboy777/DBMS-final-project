from django.urls import path, include
from . import views
from django.contrib.auth import views as auth_views
from django.contrib import admin
urlpatterns = [
    path('', views.index, name='index'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('search/', views.search_product, name='search_product'),
    path('add/', views.add_to_inventory, name='add_to_inventory'),
]