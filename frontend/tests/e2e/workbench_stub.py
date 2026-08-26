from http.server import BaseHTTPRequestHandler, HTTPServer
import json


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/v1/auth/me'):
            payload = {
                'code': 'OK', 'message': 'ok', 'request_id': 'smoke',
                'data': {'user': {
                    'id': 1, 'name': '管理员', 'phone': '13800000000', 'status': 'active',
                    'roles': [{'id': 1, 'code': 'admin', 'name': '管理员'}], 'data_scopes': [],
                    'permissions': ['auth.review', 'auth.user.manage', 'auth.session.view', 'cost.view', 'cost.allocation.manage']
                }}
            }
            self.send_response(200)
        else:
            payload = {'code': 'NOT_FOUND', 'message': 'stub route', 'request_id': 'smoke', 'data': None}
            # Return an application-level error so the browser console stays clean;
            # the frontend service intentionally falls back to demo data for this smoke test.
            self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def do_POST(self):
        payload = {'code': 'OK', 'message': 'ok', 'request_id': 'smoke', 'data': None}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def log_message(self, *_):
        return


HTTPServer(('127.0.0.1', 5001), Handler).serve_forever()
