# Create this as ordercycle/middleware.py

class CustomCorsMiddleware:
    """
    Custom CORS middleware to handle file downloads and API requests
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Add CORS headers for API endpoints and file downloads
        if request.path.startswith('/api/'):
            origin = request.META.get('HTTP_ORIGIN')
            
            # List of allowed origins
            allowed_origins = [
                'http://192.168.240.29:8080',
                'http://192.168.240.29',
                'http://localhost:8080',
                'http://localhost:8000',
                'http://localhost',
                'http://127.0.0.1:8080',
                'http://127.0.0.1:8000',
                'http://127.0.0.1'
            ]
            
            if origin in allowed_origins:
                response['Access-Control-Allow-Origin'] = origin
                response['Access-Control-Allow-Credentials'] = 'true'
                response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response['Access-Control-Allow-Headers'] = (
                    'Origin, Content-Type, Accept, Authorization, '
                    'X-Requested-With, X-CSRFToken, Cache-Control, Pragma'
                )
        
        return response