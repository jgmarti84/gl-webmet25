# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from . import models
from . import serializers
from rest_framework import viewsets
from rest_framework import generics
# from django_filters.rest_framework import DjangoFilterBackend
from datetime import datetime
from django.utils import timezone
# import pytz
from rest_framework.response import Response
# from rest_framework.decorators import list_route
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework import status
from time import time
from .models import RadarImage, Radar
import sys, os
from dateutil import parser
import shutil
from django.http import FileResponse, HttpResponse
from django.conf import settings

class RadarView(viewsets.ReadOnlyModelViewSet):
    """
    Devuelve un json con los datos de los radares.
    _____________________________________________

    Si desea una lista, consulte la url: /radar_api/radares/return_codes

    """
    serializer_class = serializers.RadarSerializer

    @action(detail=False, methods=['get'], url_path='return_codes')
    def return_codes(self, request, pk=None):
        """
        *This method return a list of radar codes
        """
        queryset = models.Radar.objects.all().values_list('code')
        ret = []
        for radar in queryset:
            ret.append(radar[0])
        return Response(ret)

    @action(detail=False, methods=['get'], url_path='return_active_codes')
    def return_active_codes(self, request, pk=None):
        """
        *This method return a list of active radar codes
        """
        queryset = models.Radar.objects.filter(is_active=True).values_list('code')
        ret = []
        for radar in queryset:
            ret.append(radar[0])
        return Response(ret)

    def get_queryset(self):
        queryset = models.Radar.objects.all()
        return queryset


class MinRadarProductView(viewsets.ReadOnlyModelViewSet):
    """
    Devuelve un json con los datos de los productos de radar.
    _____________________________________________

    Si desea una lista, consulte la url: /radar_api/radares_prod/return_keys

    """
    serializer_class = serializers.MinRadarProductSerializer

    @action(detail=False, methods=['get'], url_path='return_keys')
    def return_codes(self, request, pk=None):
        """
        *This method return a list of radar products codes
        """
        queryset = models.RadarProduct.objects.filter(enabled=True).values_list('product_key')
        ret = []
        for rp in queryset:
            ret.append(rp[0])
        return Response(ret)

    def get_queryset(self):
        queryset = models.RadarProduct.objects.all()
        return queryset


class EstrategiasView(viewsets.ReadOnlyModelViewSet):
    serializer_class = serializers.EstrategiaSerializer

    def get_queryset(self):
        queryset = models.Estrategia.objects.all()
        return queryset


class RadarImageView(viewsets.ModelViewSet):
    serializer_class = serializers.RadarImageSerializer

    def get_queryset(self):
        # /api_radares/radaresImage?date_from=2017-07-07 17:41&date_to=2017-07-07 17:50&polarimetric_var=TV&code_radar=234
        # mas o menos asi va la url
        queryset = models.RadarImage.objects.filter(show_me=True)
        date_from, date_to = None, None
        try:
            date_from = datetime.strptime(self.request.query_params.get('date_from', None), "%Y-%m-%d %H:%M") # type: ignore
            date_to = datetime.strptime(self.request.query_params.get('date_to', None), "%Y-%m-%d %H:%M") # type: ignore
        except:
            pass
        polarimetric_var = self.request.query_params.get('polarimetric_var', None) # type: ignore
        code_radar = self.request.query_params.get('code_radar', None) # type: ignore
        if polarimetric_var is not None:
            queryset = queryset.filter(polarimetric_var__in=polarimetric_var.split('-'))
        if code_radar is not None:
            queryset = queryset.filter(radar_id=code_radar)
        if (date_from and date_to) is not None:
            print(date_from, date_to)
            queryset = queryset.filter(date__range=(timezone.make_aware(date_from, timezone.get_default_timezone()), # type: ignore
                                                    timezone.make_aware(date_to, timezone.get_default_timezone()))) # type: ignore
            print(queryset)
        return queryset

    @action(detail=False, methods=['get'], url_path='filtered')
    def filtered(self, request):
        """
        API endpoint to get radar images with radar metadata (location) for map visualization.
        
        Query parameters:
          - date_from: ISO format datetime (e.g., 2025-12-05T23:00:00Z)
          - date_to: ISO format datetime (e.g., 2025-12-06T00:10:00Z)
          - radar_code: Filter by radar code (e.g., RMA3)
          - polarimetric_var: Filter by polarimetric variable (e.g., DBZH,VRAD)
        
        Returns:
          {
            "images": [
              {
                "id": 123,
                "radar_code": "RMA3",
                "radar_lat": 40.123,
                "radar_long": -3.456,
                "image_url": "/media/radares/images/RMA3/2025/12/05/...",
                "polarimetric_var": "DBZH",
                "date": "2025-12-05T23:10:00Z",
                "sweep": 0.0
              },
              ...
            ],
            "radars": {
              "RMA3": {
                "code": "RMA3",
                "title": "Radar Centro",
                "lat": 40.123,
                "long": -3.456,
                "is_active": true
              }
            }
          }
        """
        queryset = self.get_queryset()

        # Parse query params
        date_from_str = request.query_params.get('date_from', None)
        date_to_str = request.query_params.get('date_to', None)
        radar_code = request.query_params.get('radar_code', None)
        polarimetric_vars = request.query_params.get('polarimetric_var', None)

        # Filter by date range (ISO 8601)
        if date_from_str and date_to_str:
            try:
                date_from = parser.isoparse(date_from_str)
                date_to = parser.isoparse(date_to_str)
                queryset = queryset.filter(date__range=(date_from, date_to))
            except Exception as e:
                return Response(
                    {'error': f'Invalid date format: {e}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Filter by radar code
        if radar_code:
            queryset = queryset.filter(radar__code=radar_code)

        # Filter by polarimetric variable (comma-separated)
        if polarimetric_vars:
            var_list = [v.strip() for v in polarimetric_vars.split(',')]
            queryset = queryset.filter(polarimetric_var__in=var_list)

        # Order by date descending
        queryset = queryset.order_by('-date')[:500]  # Limit to 500 images

        # Build response with radar metadata
        images_data = []
        radars_data = {}

        for img in queryset:
            radar = img.radar
            if radar.code not in radars_data:
                radars_data[radar.code] = {
                    'code': radar.code,
                    'title': radar.title,
                    'lat': float(radar.center_lat),
                    'long': float(radar.center_long),
                    'is_active': radar.is_active,
                    'img_radio': radar.img_radio,
                }

            images_data.append({
                'id': img.id,
                'radar_code': radar.code,
                'radar_lat': float(radar.center_lat),
                'radar_long': float(radar.center_long),
                'image_url': img.image.url if img.image else None,
                'image_path': str(img.image) if img.image else None,
                'polarimetric_var': img.polarimetric_var,
                'date': img.date.isoformat(),
                'sweep': float(img.sweep),
                'strategy': img.strategy,
                'scanning': img.scanning,
                # Direct serve URL from product_output
                'product_image_url': f'/radar_api/serve_image/?path=RMA3/{img.date.year}/{img.date.month:02d}/{img.date.day:02d}/{radar.code}_{img.date.strftime("%Y%m%dT%H%M%SZ")}_{img.polarimetric_var}_{img.scanning:02d}.png',
            })

        return Response({
            'images': images_data,
            'radars': radars_data,
            'count': len(images_data),
        })



class AddImagesView(APIView):
    def get(self, request, *args, **kw):
        # TODO: CUANDO LOS RADARES NO ESTAN ACTiVOS, EL SHOWME (de RadarImage) ESTA EN FALSE
        # New images RMA5_9005_03_20170727T200850Z_1.98_COLMAX.png

        start_time = time()
        objs = []
        # source es donde se encuentran las imagenes
        source = "/import_images/"
        # media_path es donde esta el path del media
        media_path = "/app/website/media/radares/images"
        count_files = 0
        for path, subdirs, files in os.walk(source):
            for name in files:
                if name.endswith(".png"):
                    count_files += 1
                    #RMA5_9005_03_20170727T200850Z_1.98_COLMAX.png
                    radar_code, strategy, scanning, date, sweep, polarimetric_var = name.split("_")
                    try:
                        radar = Radar.objects.get(code=radar_code)
                        if radar.is_active:
                            show = True
                        else:
                            show = False
                    except:
                        show = False
                    dt = parser.parse(date)
                    # Copy image
                    folder = os.path.join(str(radar_code), str(dt.year), str(dt.month), str(dt.day), name)
                    new_path = os.path.join(media_path, folder)
                    old_path = os.path.join(path, name)
                    shutil.move(old_path, new_path)
                    radar_image = RadarImage(radar=radar,
                                             image=os.path.join("radares/images", folder),
                                             polarimetric_var=polarimetric_var.replace(".png", ""),
                                             date=dt,
                                             strategy=strategy,
                                             scanning=scanning,
                                             sweep=sweep,
                                             show_me=show
                                             )
                    objs.append(radar_image)
                    #                    if len(objs) == 999:
                    #                        RadarImage.objects.bulk_create(objs)
                    #                        del objs[:]
        RadarImage.objects.bulk_create(objs)
        del objs[:]
        elapsed_time = time() - start_time
        print("Listo. Elapsed time: {:0.10f} minutos. Archivos: {}".format(elapsed_time / 60, count_files))

        response = Response("Listo. Elapsed time: {:0.10f} minutos. Archivos: {}".format(elapsed_time / 60, count_files), status=status.HTTP_200_OK)
        return response


class AddOLDImagesView(APIView):
    def get(self, request, *args, **kw):
        # TODO: CUANDO LOS RADARES NO ESTAN ACTiVOS, EL SHOWME (de RadarImage) ESTA EN FALSE
        # New images RMA5_9005_03_20170727T200850Z_1.98_COLMAX.png

        start_time = time()
        objs = []
        # source es donde se encuentran las imagenes
        source = "/app/website/media/radares/images"
        # media_path es donde esta el path del media
        media_path = "/app/website/media/radares/historic_images"
        count_files = 0
        for path, subdirs, files in os.walk(source):
            for name in files:
                if name.endswith(".png"):
                    count_files += 1
                    #RMA5_9005_03_20170727T200850Z_1.98_COLMAX.png
                    #Colmax_RMA1_0117_01_TH_20170228T141917Z.png
                    error = True
                    try:
                        colmax, radar_code, strategy, scanning, polarimetric_var, date = name.split("_")
                        try:
                            radar = Radar.objects.get(code=radar_code)
                            if radar.is_active:
                                show = True
                            else:
                                show = False
                        except:
                            show = False
                        dt = parser.parse(date.replace(".png", ""))
                        # Copy image
                        folder = os.path.join(str(radar_code), str(dt.year), str(dt.month), str(dt.day), name)
                        new_path = os.path.join(media_path, folder)
                        old_path = os.path.join(path, name)
                        print(old_path)
                        print(new_path)
                        error = False
                    except:
                        print(name.split("_"))

                    if not error:
                        os.renames(old_path, new_path)
                        #shutil.move(old_path, new_path)
                        radar_image = RadarImage(radar=radar,
                                                 image=os.path.join("radares/images", folder),
                                                 polarimetric_var='COLMAX', #polarimetric_var.replace(".png", ""),
                                                 date=dt,
                                                 strategy=strategy,
                                                 scanning=scanning,
                                                 sweep=0,
                                                 show_me=show
                                                 )
                        objs.append(radar_image)
                        #                    if len(objs) == 999:
                        #                        RadarImage.objects.bulk_create(objs)
                        #                        del objs[:]
        RadarImage.objects.bulk_create(objs)
        del objs[:]
        elapsed_time = time() - start_time
        print("Listo. Elapsed time: {:0.10f} minutos. Archivos: {}".format(elapsed_time / 60, count_files))

        response = Response("Listo. Elapsed time: {:0.10f} minutos. Archivos: {}".format(elapsed_time / 60, count_files), status=status.HTTP_200_OK)
        return response


class ServeProductImageView(APIView):
    """
    Serve PNG images directly from product_output folder.
    URL: /radar_api/serve_image/RMA3/2025/12/05/RMA3_20251205T231000Z_DBZH_00.png
    """
    def get(self, request, *args, **kwargs):
        # Get the image path from URL parameters or query string
        image_path = request.query_params.get('path', '')
        if not image_path:
            return Response(
                {'error': 'Missing path parameter'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Security: only allow paths under /app/product_output/
        full_path = os.path.join('/app/product_output', image_path.lstrip('/'))
        full_path = os.path.abspath(full_path)  # resolve .. and such
        base_path = os.path.abspath('/app/product_output')

        if not full_path.startswith(base_path) or not os.path.isfile(full_path):
            return Response(
                {'error': 'Image not found or invalid path'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Serve the file
        try:
            return FileResponse(
                open(full_path, 'rb'),
                content_type='image/png',
                as_attachment=False
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

