"""
Admin configuration for radar_viewer application.
"""

from django.contrib import admin
from .models import RadarProduct, RadarStation


@admin.register(RadarProduct)
class RadarProductAdmin(admin.ModelAdmin):
    """Admin configuration for RadarProduct model."""
    
    list_display = ['name', 'product_type', 'valid_time', 'created_at']
    list_filter = ['product_type', 'created_at']
    search_fields = ['name', 'file_path']
    date_hierarchy = 'valid_time'


@admin.register(RadarStation)
class RadarStationAdmin(admin.ModelAdmin):
    """Admin configuration for RadarStation model."""
    
    list_display = ['code', 'name', 'latitude', 'longitude', 'is_active']
    list_filter = ['is_active']
    search_fields = ['code', 'name']
