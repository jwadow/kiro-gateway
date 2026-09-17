from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from typing_extensions import override


class PrivateNetworkCORSMiddleware(CORSMiddleware):
    @override
    def preflight_response(self, request_headers: Headers) -> Response:
        response = super().preflight_response(request_headers)
        if (
            response.status_code == 200
            and request_headers.get("access-control-request-private-network") == "true"
        ):
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response
