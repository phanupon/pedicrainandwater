"""
ASGI config for flood_project project.
Supports WebSocket via Django Channels.
"""
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import flood_alert.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'flood_project.settings')

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AuthMiddlewareStack(
        URLRouter(flood_alert.routing.websocket_urlpatterns)
    ),
})
