"""
AgentForge — Photoshop tools via adb-mcp UXP plugin.

53 tools for controlling Adobe Photoshop.
Communication: Socket.IO → adb-mcp proxy → UXP Plugin → Photoshop

Requires:
- Adobe Photoshop 26.0+ with UXP Developer Mode
- adb-mcp proxy running: node adb-mcp/adb-proxy-socket/proxy.js
"""

import json
import logging
from typing import Any, Dict, Optional

from agentforge.tools import Tool, ToolRegistry, ToolResult
from agentforge.runtime_config import load_tool_timeout_config

logger = logging.getLogger(__name__)


class PhotoshopClient:
    """Client for communicating with Photoshop via adb-mcp Socket.IO proxy."""
    _client = None
    _connected = False

    @classmethod
    def connect(cls, url: str = "http://localhost:3000"):
        """Connect to the adb-mcp proxy."""
        if cls._connected:
            return
        try:
            import socketio
            cls._client = socketio.Client()
            cls._client.connect(url)
            cls._connected = True
        except ImportError:
            raise ImportError("python-socketio not installed. Run: pip install python-socketio")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to Photoshop proxy at {url}: {e}")

    @classmethod
    def send(cls, command: str, params: Dict = None) -> Any:
        """Send a command to Photoshop and wait for response."""
        if not cls._connected:
            cls.connect()

        import threading
        result = {"data": None, "error": None}
        event = threading.Event()

        def on_response(data):
            result["data"] = data
            event.set()

        def on_error(data):
            result["error"] = data
            event.set()

        cls._client.emit("ps_command", {
            "command": command,
            "params": params or {}
        })

        # Simple response handling - in production would use proper callback
        cls._client.on("ps_response", on_response)
        cls._client.on("ps_error", on_error)

        timeout_s = load_tool_timeout_config().photoshop_s
        if not event.wait(timeout=timeout_s):
            return ToolResult.error_result(
                f"Photoshop command timed out after {timeout_s}s: {command}"
            )

        if result["error"]:
            return ToolResult(success=False, output=None, error=str(result["error"]))
        return ToolResult(success=True, output=result["data"])

    @classmethod
    def disconnect(cls):
        if cls._client and cls._connected:
            cls._client.disconnect()
            cls._connected = False


def _make_ps_tool(command: str, description: str, schema: Dict) -> callable:
    """Factory for creating Photoshop tool execute functions."""
    def execute(args: Dict[str, Any]) -> ToolResult:
        try:
            return PhotoshopClient.send(command, args)
        except ImportError as e:
            return ToolResult.from_exception(e, context="Photoshop dependency error", logger=logger)
        except ConnectionError as e:
            return ToolResult.from_exception(e, context="Photoshop connection error", logger=logger)
        except Exception as e:
            return ToolResult.from_exception(e, context="Photoshop command failed", logger=logger)
    return execute


# Tool definitions — all 53 Photoshop tools
PS_TOOLS = [
    # Document
    ("ps_create_document", "Create a new Photoshop document.", {"width": "int", "height": "int", "name": "string", "resolution": "int"}),
    ("ps_open_document", "Open an existing PSD/image file.", {"path": "string"}),
    ("ps_save_document", "Save the current document.", {"path": "string", "format": "string"}),
    ("ps_close_document", "Close the current document.", {"save": "boolean"}),
    ("ps_get_document_info", "Get info about the active document.", {}),
    # Layer Management
    ("ps_create_layer", "Create a new layer.", {"name": "string", "type": "string"}),
    ("ps_delete_layer", "Delete a layer.", {"name": "string"}),
    ("ps_select_layer", "Select a layer by name.", {"name": "string"}),
    ("ps_rename_layer", "Rename a layer.", {"old_name": "string", "new_name": "string"}),
    ("ps_set_layer_visibility", "Show/hide a layer.", {"name": "string", "visible": "boolean"}),
    ("ps_set_layer_opacity", "Set layer opacity.", {"name": "string", "opacity": "number"}),
    ("ps_move_layer", "Move a layer.", {"name": "string", "x": "number", "y": "number"}),
    ("ps_resize_layer", "Resize a layer.", {"name": "string", "width": "number", "height": "number"}),
    ("ps_duplicate_layer", "Duplicate a layer.", {"name": "string"}),
    ("ps_merge_layers", "Merge selected layers.", {"layers": "array"}),
    ("ps_group_layers", "Group layers.", {"layers": "array", "group_name": "string"}),
    ("ps_set_layer_blend_mode", "Set blend mode.", {"name": "string", "mode": "string"}),
    ("ps_lock_layer", "Lock/unlock a layer.", {"name": "string", "locked": "boolean"}),
    ("ps_rasterize_layer", "Rasterize a layer.", {"name": "string"}),
    # Text
    ("ps_create_text_layer", "Create a text layer.", {"text": "string", "x": "number", "y": "number", "font": "string", "size": "number"}),
    ("ps_edit_text", "Edit text content.", {"layer": "string", "text": "string"}),
    ("ps_set_text_style", "Set text styling.", {"layer": "string", "font": "string", "size": "number", "color": "string"}),
    # Drawing
    ("ps_fill_layer", "Fill a layer with color.", {"color": "string", "opacity": "number"}),
    ("ps_stroke_layer", "Add stroke to layer.", {"color": "string", "width": "number"}),
    ("ps_draw_rectangle", "Draw a rectangle.", {"x": "number", "y": "number", "width": "number", "height": "number", "color": "string"}),
    ("ps_draw_ellipse", "Draw an ellipse.", {"x": "number", "y": "number", "width": "number", "height": "number", "color": "string"}),
    ("ps_draw_line", "Draw a line.", {"x1": "number", "y1": "number", "x2": "number", "y2": "number", "color": "string", "width": "number"}),
    # Filters
    ("ps_apply_gaussian_blur", "Apply Gaussian blur.", {"radius": "number"}),
    ("ps_apply_sharpen", "Apply sharpen filter.", {"amount": "number"}),
    ("ps_apply_brightness_contrast", "Adjust brightness/contrast.", {"brightness": "number", "contrast": "number"}),
    ("ps_apply_hue_saturation", "Adjust hue/saturation.", {"hue": "number", "saturation": "number", "lightness": "number"}),
    ("ps_apply_levels", "Adjust levels.", {"input_min": "number", "input_max": "number", "output_min": "number", "output_max": "number"}),
    ("ps_apply_curves", "Adjust curves.", {"points": "array"}),
    ("ps_apply_color_balance", "Adjust color balance.", {"shadows": "array", "midtones": "array", "highlights": "array"}),
    ("ps_apply_noise", "Add noise.", {"amount": "number", "distribution": "string"}),
    ("ps_apply_drop_shadow", "Apply drop shadow.", {"angle": "number", "distance": "number", "spread": "number", "size": "number", "color": "string"}),
    # Canvas
    ("ps_crop", "Crop the canvas.", {"x": "number", "y": "number", "width": "number", "height": "number"}),
    ("ps_resize_canvas", "Resize the canvas.", {"width": "number", "height": "number", "anchor": "string"}),
    ("ps_resize_image", "Resize the image.", {"width": "number", "height": "number", "resample": "string"}),
    ("ps_rotate_canvas", "Rotate the canvas.", {"angle": "number"}),
    ("ps_flip_canvas", "Flip the canvas.", {"direction": "string"}),
    # Color
    ("ps_set_foreground_color", "Set foreground color.", {"color": "string"}),
    ("ps_set_background_color", "Set background color.", {"color": "string"}),
    # Selection
    ("ps_make_selection", "Make a selection.", {"x": "number", "y": "number", "width": "number", "height": "number", "type": "string"}),
    ("ps_deselect", "Deselect all.", {}),
    ("ps_invert_selection", "Invert the selection.", {}),
    ("ps_feather_selection", "Feather the selection.", {"radius": "number"}),
    # Export
    ("ps_export_png", "Export as PNG.", {"path": "string", "quality": "number"}),
    ("ps_export_jpg", "Export as JPEG.", {"path": "string", "quality": "number"}),
    ("ps_export_layer", "Export a single layer.", {"layer": "string", "path": "string", "format": "string"}),
    # Utility
    ("ps_get_active_layer", "Get info about the active layer.", {}),
    ("ps_undo", "Undo last action.", {}),
    ("ps_redo", "Redo last undone action.", {}),
]


def register(registry: ToolRegistry, skill_name: str = "photoshop") -> None:
    """Register all 53 Photoshop tools."""
    tools = []
    for name, description, params in PS_TOOLS:
        schema = {
            "type": "object",
            "properties": {k: {"type": v} for k, v in params.items()},
        }
        tools.append(Tool(
            name=name,
            description=description,
            input_schema=schema,
            execute_fn=_make_ps_tool(name.replace("ps_", ""), description, schema),
        ))
    registry.register_skill(skill_name, tools)
