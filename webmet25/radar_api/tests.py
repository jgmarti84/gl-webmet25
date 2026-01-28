"""
This file contains test cases for the radar_api application.
"""

from django.test import TestCase
from .models import Radar, Estrategia, RadarImage, Reference, Volumen, RadarProduct

class RadarTests(TestCase):
    def setUp(self):
        # Set up any initial data for your tests here
        pass

    def test_example(self):
        # Replace with an actual test case
        self.assertEqual(1 + 1, 2)

    # Add more test cases as needed
