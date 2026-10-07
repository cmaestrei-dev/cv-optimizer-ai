"""Límite de tamaño del cuerpo de las peticiones.

FastAPI lee el formulario (y Starlette guarda los archivos en disco) ANTES de verificar el token, así
que sin este límite cualquiera podría llenar el disco con una subida enorme. Se corta por la cabecera
Content-Length y, si no viene, contando lo que llega.
"""

import json

MAX_BODY_BYTES = 6_000_000  # el PDF más grande aceptado (5 MB) + margen del formulario


class _TooLargeError(Exception):
    pass


async def _reject(send) -> None:
    body = json.dumps({"detail": "La petición es demasiado grande."}).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class BodySizeLimit:
    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = dict(scope.get("headers", [])).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > self.max_bytes):
            return await _reject(send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _TooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _TooLargeError:
            await _reject(send)
