"""
URL configuration for radar_viewer application.
"""
from django.urls import path
from . import views
# #!/usr/bin/python
# # -*- coding: utf-8 -*-
# from django.conf.urls import url
# from django.contrib.auth import views as auth_views
# from . import views

# urlpatterns = [
#                 url(r'^$', views.home, name='main'),
#                ]

app_name = 'frontend'

urlpatterns = [
    path('', views.home, name='main'),
]
