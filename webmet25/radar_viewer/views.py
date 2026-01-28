"""
Views for radar_viewer application.

Provides views for the map-based radar visualization interface.
"""

from django.shortcuts import render
from django.http import JsonResponse
from .models import RadarProduct, RadarStation


def index(request):
    """Main map view for radar visualization."""
    return render(request, 'radar_viewer/index.html')


def api_products(request):
    """API endpoint to get available radar products."""
    products = RadarProduct.objects.all().order_by('-valid_time')[:50]
    data = [
        {
            'id': p.id,
            'name': p.name,
            'type': p.product_type,
            'file_path': p.file_path,
            'valid_time': p.valid_time.isoformat(),
            'latitude': p.latitude,
            'longitude': p.longitude,
        }
        for p in products
    ]
    return JsonResponse({'products': data})


def api_stations(request):
    """API endpoint to get radar stations."""
    stations = RadarStation.objects.filter(is_active=True)
    data = [
        {
            'id': s.id,
            'code': s.code,
            'name': s.name,
            'latitude': s.latitude,
            'longitude': s.longitude,
            'altitude': s.altitude,
        }
        for s in stations
    ]
    return JsonResponse({'stations': data})
