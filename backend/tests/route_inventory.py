"""Enumerate effective routes across supported FastAPI router representations."""
from fastapi.routing import APIRoute


def api_routes(app):
    for route in app.routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, 'effective_route_contexts'):
            for context in route.effective_route_contexts():
                if isinstance(context.original_route, APIRoute):
                    yield context
