"""
Django application configuration for radar_viewer.
"""

from django.apps import AppConfig


class RadarViewerConfig(AppConfig):
    """Configuration for the radar_viewer application."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'radar_viewer'
    verbose_name = 'Radar Viewer'
