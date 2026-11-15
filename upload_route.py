"""HTTP endpoint behind the 'Choose file...' button of Load Script File (only exists inside ComfyUI)."""
from aiohttp import web
from server import PromptServer

from .nodes import MAX_BYTES, save_upload


@PromptServer.instance.routes.post("/shot_script/upload")
async def upload_script(request):
    form = await request.post()
    field = form.get("file")
    if field is None or not hasattr(field, "file"):
        return web.json_response({"error": "no file in the request"}, status=400)
    data = field.file.read(MAX_BYTES + 1)
    try:
        name = save_upload(field.filename, data)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    return web.json_response({"name": name})

