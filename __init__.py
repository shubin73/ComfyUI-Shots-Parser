from .nodes import LoadScriptFile, ShotScriptParser

NODE_CLASS_MAPPINGS = {
    "LoadScriptFile": LoadScriptFile,
    "ShotScriptParser": ShotScriptParser,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadScriptFile": "Load Script File",
    "ShotScriptParser": "Shot Script Parser",
}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
