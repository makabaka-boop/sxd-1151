"""
WSGI config for farm_inspection project.
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'farm_inspection.settings')
application = get_wsgi_application()
