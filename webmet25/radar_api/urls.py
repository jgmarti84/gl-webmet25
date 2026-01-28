from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'radar_api'

router = DefaultRouter()
router.register(r'radares', views.RadarView, basename='radares')
router.register(r'estrategias', views.EstrategiasView, basename='estrategias')
router.register(r'images_radares', views.RadarImageView, basename='images_radares')
router.register(r'radares_prod', views.MinRadarProductView, basename='radares_prod')

urlpatterns = [
    # include router urls with an explicit app_name so the namespace works correctly
    path('', include((router.urls, app_name), namespace='api')),

    # explicit class-based views (use unique names)
    path('serve_image/', views.ServeProductImageView.as_view(), name='serve_image'),
    path('add_images/', views.AddImagesView.as_view(), name='add_images_view'),
    path('add_old_images/', views.AddOLDImagesView.as_view(), name='add_old_images_view'),
]

