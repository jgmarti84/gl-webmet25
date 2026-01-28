from django.core.management.base import BaseCommand
from django.core.serializers import deserialize
from django.db import transaction
from django.conf import settings
import os
import json

class Command(BaseCommand):
    help = "Seed radar_api from radar_api/fixtures/initial_data.json (deserializes JSON fixture)."

    def find_fixture(self):
        candidates = [
            os.path.join(os.getcwd(), 'radar_api', 'fixtures', 'initial_data.json'),
        ]
        if getattr(settings, 'BASE_DIR', None):
            candidates.append(os.path.join(settings.BASE_DIR, 'radar_api', 'fixtures', 'initial_data.json'))
        # relative to this file
        here = os.path.abspath(os.path.dirname(__file__))
        candidates.append(os.path.abspath(os.path.join(here, '..', '..', 'fixtures', 'initial_data.json')))

        for p in candidates:
            if p and os.path.exists(p):
                return p
        return None

    def handle(self, *args, **options):
        fixture_path = self.find_fixture()
        if not fixture_path:
            self.stderr.write(self.style.ERROR("Fixture not found: radar_api/fixtures/initial_data.json"))
            return
        # Load the raw fixture JSON so we can control the save order
        with open(fixture_path, 'r', encoding='utf-8') as fh:
            try:
                raw = json.load(fh)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f'Error parsing JSON fixture: {exc}'))
                return

        created = 0
        updated = 0

        def _process_entries(entries):
            nonlocal created, updated
            if not entries:
                return
            # deserialize requires a file-like or string containing a JSON list
            json_text = json.dumps(entries)
            for des_obj in deserialize('json', json_text):
                model = des_obj.object.__class__
                pk = des_obj.object.pk
                exists = model.objects.filter(pk=pk).exists() if pk is not None else False
                des_obj.save()
                if exists:
                    updated += 1
                else:
                    created += 1

        with transaction.atomic():
            # 1) ensure RadarProduct rows are created first to satisfy FK relations from Reference
            rp_entries = [e for e in raw if e.get('model') == 'radar_api.radarproduct']
            _process_entries(rp_entries)

            # 2) process remaining entries in the fixture (excluding those already processed)
            remaining = [e for e in raw if e.get('model') != 'radar_api.radarproduct']
            _process_entries(remaining)

        self.stdout.write(self.style.SUCCESS(f'Seed completed: {created} created, {updated} updated from {fixture_path}'))