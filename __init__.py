from .nodes import LoadScriptFile, ShotScriptParser

try:                                    # the upload endpoint needs ComfyUI's web server (absent in unit tests)
    from . import upload_route          # noqa: F401
except ImportError:
    pass

NODE_CLASS_MAPPINGS = {
    "LoadScriptFile": LoadScriptFile,
    "ShotScriptParser": ShotScriptParser,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadScriptFile": "Load Script File",
    "ShotScriptParser": "Shot Script Parser",
}
WEB_DIRECTORY = "./js"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
