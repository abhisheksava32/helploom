"""WSGI entry point. Production serves ASGI (daphne) so websockets work; this exists for
management tooling and plain HTTP hosting."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "helploom.settings")

application = get_wsgi_application()
