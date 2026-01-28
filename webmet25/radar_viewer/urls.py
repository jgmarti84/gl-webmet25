"""
URL configuration for radar_viewer application.
"""

from django.urls import path
from . import views

app_name = 'radar_viewer'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/products/', views.api_products, name='api_products'),
    path('api/stations/', views.api_stations, name='api_stations'),
]
