from django.db import models
from  math import cos
from decimal import Decimal


class Radar(models.Model):
    RADIO_CHOICES = ((120, '120km'),
                     (240, '240km'),
                     (480, '480km'),)
    code = models.CharField('Cod. Radar', max_length=16, primary_key=True)
    title = models.CharField('Tit. Radar', max_length=64)
    description = models.CharField('Descrip.', max_length=64)
    center_lat = models.DecimalField('Latitud centro', max_digits=12, decimal_places=8)
    center_long = models.DecimalField('Longitud centro', max_digits=12, decimal_places=8)
    img_radio = models.IntegerField('Rádio de la Imagen (kmts)', choices=RADIO_CHOICES)
    is_active = models.BooleanField('Radar activo?', default=True)
    point1_lat = models.DecimalField('Latitud Norte', max_digits=14, decimal_places=10, default=Decimal('0'))
    point1_long = models.DecimalField('Longitud Este', max_digits=14, decimal_places=10, default=Decimal('0'))
    point2_lat = models.DecimalField('Latitud Sur', max_digits=14, decimal_places=10, default=Decimal('0'))
    point2_long = models.DecimalField('Longitud Oeste', max_digits=14, decimal_places=10, default=Decimal('0'))

    def __str__(self):
        return '{} - {}'.format(self.code, self.title)

    def get_extent(self):
        lat_max = float(self.center_lat) + float(self.img_radio) / 111.325
        lat_min = float(self.center_lat) - float(self.img_radio) / 111.325
        kmts_grado_by_la = cos(self.center_lat) * 111.325
        long_max = float(self.center_long) + float(self.img_radio) / kmts_grado_by_la
        long_min = float(self.center_long) - float(self.img_radio) / kmts_grado_by_la
        return lat_max, lat_min, long_max, long_min

    class Meta:
        verbose_name = 'Radar'
        verbose_name_plural = 'Radares'


class RadarImage(models.Model):
    radar = models.ForeignKey(Radar, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='radares/images')
    polarimetric_var = models.CharField('Variable Polarimétrica', max_length=10, default='')
    date = models.DateTimeField('Fecha y hora')
    strategy = models.IntegerField('Estrategia', default=0)
    scanning = models.IntegerField('Num. Barrido', default=0)
    sweep = models.DecimalField('Ángulo de la elevacion', max_digits=4, decimal_places=2, default=Decimal('0'))
    show_me = models.BooleanField('Se muestra?', default=True)


    def __str__(self):
        return '{}_{}_{}'.format(self.date, self.radar, self.polarimetric_var)

    class Meta:
        verbose_name = 'Imagen de Radar'
        verbose_name_plural = 'Imagenes de Radares'


class RadarProduct(models.Model):
    product_key = models.CharField('Código de Producto (Nombre de la imagen)', max_length=10, default='')
    product_title = models.CharField('Título de Producto', max_length=10, default='')
    product_description = models.TextField('Descripción de Producto', default='')
    enabled = models.BooleanField('Se muestra?', default=True)
    see_in_open = models.BooleanField('Mostrar al inicio', default=False)

    def __str__(self):
        return '{} ({})'.format(self.product_key, self.product_title)

    class Meta:
        verbose_name = 'Producto de Radar'
        verbose_name_plural = 'Productos de Radar'
        ordering = ['product_key']


class Reference(models.Model):
    product = models.ForeignKey(RadarProduct, on_delete=models.CASCADE, related_name='references')
    title = models.CharField('Referencia', max_length=64, default='')
    description = models.CharField('Descripción', max_length=255, default='')
    unit = models.CharField('Unidad', max_length=64, default='')
    value = models.FloatField('Valor', default=0)
    color = models.CharField('Color (RGB con # al principio)', max_length=7, default='#000000')
    color_font = models.CharField('Color de texto (RGB con # al principio)', max_length=7, default='#FFFFFF')

    class Meta:
        ordering = ['-value']
        verbose_name = 'Referencia'
        verbose_name_plural = 'Referencias'


class Volumen(models.Model):
    value = models.IntegerField('Valor', default=0)

    def __str__(self):
        return '{}'.format(self.value)

    class Meta:
        verbose_name = 'Volumen'
        verbose_name_plural = 'Volumenes'


class Estrategia(models.Model):
    code = models.CharField('ID de Estrategia', max_length=16, primary_key=True)
    description = models.CharField('Descripción', max_length=255, default='')
    volumenes = models.ManyToManyField(Volumen, related_name='estrategias')

    def __str__(self):
        return '{}'.format(self.code)

    class Meta:
        verbose_name = 'Volumen'
        verbose_name_plural = 'Estrategias'