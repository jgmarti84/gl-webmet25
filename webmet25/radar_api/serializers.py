from rest_framework import serializers
from .models import Radar, RadarProduct, Estrategia, RadarImage  # Replace with your actual model name


class RadarSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Radar
        fields = ('code', 'title', 'description', 'center_lat',
                  'center_long','img_radio',
                  'point1_lat','point1_long',
                  'point2_lat','point2_long',)

        extra_kwargs = {
            'url': {'view_name': 'radar-detail', 'lookup_field': 'url'},
        }


class MinRadarSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Radar
        fields = ('code',)
        extra_kwargs = {
            'url': {'view_name': 'radar-detail', 'lookup_field': 'url'},
        }


class MinRadarProductSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = RadarProduct
        fields = ('product_key','product_title','product_description')


class EstrategiaSerializer(serializers.HyperlinkedModelSerializer):
    volumenes = serializers.StringRelatedField(many=True)

    class Meta:
        model = Estrategia
        fields = ('code', 'volumenes')


class RadarImageSerializer(serializers.HyperlinkedModelSerializer):
    radar_code = serializers.ReadOnlyField(source='radar.code', read_only=True)

    class Meta:
        model = RadarImage
        fields = ('radar_code', 'image', 'polarimetric_var', 'date', 'strategy', 'scanning')
        extra_kwargs = {
            'url': {'view_name': 'radarImage-detail', 'lookup_field': 'url'},
        }

    def get_serializer_context(self):
        """
        Extra context provided to the serializer class.
        """
        return {
            'request': self.context.get('request'),  # request object is passed here
            'format': self.context.get('format'),
            'view': self.context.get('view')
        }

    def create(self, validated_data):
        radar_code = self.context.get('request').data.get('code') # type: ignore
        radar_obj = Radar.objects.get(code=radar_code)
        radar_image = RadarImage.objects.create(
            radar=radar_obj,
            image=validated_data['image'],
            polarimetric_var=validated_data['polarimetric_var'],
            date=validated_data['date'],
            strategy=validated_data['strategy'],
            scanning=validated_data['scanning']
        )
        return radar_image
