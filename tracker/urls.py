from django.urls import path, include
from . import views
from django.contrib.auth import views as auth_views
from django.contrib import admin
urlpatterns = [
    path('', views.index, name='index'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('search/', views.search_product, name='search_product'),
    path('add/', views.add_to_inventory, name='add_to_inventory'),
    path('profile/', views.profile, name='profile'),
    path('update-prices/', views.update_prices, name='update_prices'),
    path('inventory/<int:product_id>/edit/', views.edit_inventory, name='edit_inventory'),
    path('register/', views.register, name='register'),
]