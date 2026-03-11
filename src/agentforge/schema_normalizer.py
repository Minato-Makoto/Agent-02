"""
Tool JSON schema normalization for provider compatibility.

Primary goals:
- Ensure top-level object schemas for function tools.
- Normalize non-standard JSON type names.
- Flatten top-level anyOf/oneOf object variants into one object schema.
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional


_TYPE_ALIASES = {
    "int": "integer",
    "integer": "integer",
    "float": "number",
    "double": "number",
    "number": "number",
    "bool": "boolean",
    "boolean": "boolean",
    "str": "string",
    "string": "string",
    "dict": "object",
    "map": "object",
    "object": "object",
    "list": "array",
    "array": "array",
}


def _normalize_type_value(value: Any) -> Any:
    if isinstance(value, str):
        return _TYPE_ALIASES.get(value.lower(), value)
    if isinstance(value, list):
        return [_normalize_type_value(v) for v in value]
    return value


def _extract_enum_values(schema: Dict[str, Any]) -> Optional[List[Any]]:
    if isinstance(schema.get("enum"), list):
        return list(schema["enum"])
    if "const" in schema:
        return [schema["const"]]
    for key in ("anyOf", "oneOf"):
        variants = schema.get(key)
        if isinstance(variants, list):
            merged: List[Any] = []
            for variant in variants:
                if isinstance(variant, dict):
                    values = _extract_enum_values(variant)
                    if values:
                        merged.extend(values)
            if merged:
                # preserve order while deduplicating
                seen = set()
                out = []
                for item in merged:
                    mark = repr(item)
                    if mark in seen:
                        continue
                    seen.add(mark)
                    out.append(item)
                return out
    return None


def _merge_property_schema(existing: Any, incoming: Any) -> Any:
    if not isinstance(existing, dict):
        return incoming
    if not isinstance(incoming, dict):
        return existing

    existing_enum = _extract_enum_values(existing)
    incoming_enum = _extract_enum_values(incoming)
    if existing_enum or incoming_enum:
        values = []
        seen = set()
        for v in (existing_enum or []) + (incoming_enum or []):
            mark = repr(v)
            if mark in seen:
                continue
            seen.add(mark)
            values.append(v)
        merged: Dict[str, Any] = {}
        for source in (existing, incoming):
            for key in ("title", "description", "default"):
                if key not in merged and key in source:
                    merged[key] = source[key]
        if values:
            merged["enum"] = values
            inferred_types = {type(v).__name__ for v in values}
            if len(inferred_types) == 1:
                one = next(iter(inferred_types))
                merged["type"] = {
                    "str": "string",
                    "int": "integer",
                    "float": "number",
                    "bool": "boolean",
                    "list": "array",
                    "dict": "object",
                }.get(one, one)
        return merged

    out = deepcopy(existing)
    for k, v in incoming.items():
        out.setdefault(k, v)
    return out


def _normalize_recursive(node: Any) -> Any:
    if isinstance(node, list):
        return [_normalize_recursive(v) for v in node]
    if not isinstance(node, dict):
        return node

    out: Dict[str, Any] = {}
    for key, value in node.items():
        if key == "type":
            out[key] = _normalize_type_value(value)
        else:
            out[key] = _normalize_recursive(value)
    return out


def normalize_tool_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a tool input schema to a provider-friendly JSON schema.

    The output always uses top-level type=object.
    """
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}, "additionalProperties": True}

    normalized = _normalize_recursive(deepcopy(schema))
    variant_key = None
    if isinstance(normalized.get("anyOf"), list):
        variant_key = "anyOf"
    elif isinstance(normalized.get("oneOf"), list):
        variant_key = "oneOf"

    if variant_key:
        variants = normalized.get(variant_key, [])
        merged_properties: Dict[str, Any] = {}
        required_counts: Dict[str, int] = {}
        variant_object_count = 0

        for variant in variants:
            if not isinstance(variant, dict):
                continue
            props = variant.get("properties")
            if not isinstance(props, dict):
                continue
            variant_object_count += 1
            for key, value in props.items():
                if key not in merged_properties:
                    merged_properties[key] = value
                else:
                    merged_properties[key] = _merge_property_schema(
                        merged_properties[key], value
                    )
            req = variant.get("required", [])
            if isinstance(req, list):
                for r in req:
                    if isinstance(r, str):
                        required_counts[r] = required_counts.get(r, 0) + 1

        required: List[str] = []
        base_required = normalized.get("required")
        if isinstance(base_required, list):
            required = [x for x in base_required if isinstance(x, str)]
        elif variant_object_count > 0:
            for key, count in required_counts.items():
                if count == variant_object_count:
                    required.append(key)

        normalized = {
            "type": "object",
            "properties": merged_properties,
            "additionalProperties": normalized.get("additionalProperties", True),
        }
        if required:
            normalized["required"] = required
        if isinstance(schema.get("title"), str):
            normalized["title"] = schema["title"]
        if isinstance(schema.get("description"), str):
            normalized["description"] = schema["description"]

    if "type" not in normalized and (
        isinstance(normalized.get("properties"), dict)
        or isinstance(normalized.get("required"), list)
    ):
        normalized["type"] = "object"

    if normalized.get("type") != "object":
        # Force function-tool top-level object schema.
        normalized = {
            "type": "object",
            "properties": normalized.get("properties", {}),
            "required": normalized.get("required", []),
            "additionalProperties": normalized.get("additionalProperties", True),
        }

    normalized.setdefault("properties", {})
    normalized.setdefault("additionalProperties", True)
    if not isinstance(normalized.get("required"), list):
        normalized["required"] = []

    return normalized


_COMMON_DROP_KEYS = {"$schema", "$id"}
_GEMINI_DROP_KEYS = {
    "$schema",
    "$id",
    "$ref",
    "$defs",
    "definitions",
    "patternProperties",
    "additionalProperties",
    "examples",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "multipleOf",
    "pattern",
    "format",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
}
_ANTHROPIC_DROP_KEYS = {"$schema", "$id", "examples"}


def _flatten_literal_union(variants: List[Any]) -> Optional[Dict[str, Any]]:
    values: List[Any] = []
    item_type: Optional[str] = None
    for v in variants:
        if not isinstance(v, dict):
            return None
        val = None
        if "const" in v:
            val = v.get("const")
        elif isinstance(v.get("enum"), list) and len(v.get("enum", [])) == 1:
            val = v["enum"][0]
        if val is None:
            return None
        t = v.get("type")
        if not isinstance(t, str):
            return None
        if item_type is None:
            item_type = t
        elif item_type != t:
            return None
        values.append(val)
    if values and item_type:
        return {"type": item_type, "enum": values}
    return None


def _clean_schema_for_provider_recursive(node: Any, provider: str) -> Any:
    if isinstance(node, list):
        return [_clean_schema_for_provider_recursive(x, provider) for x in node]
    if not isinstance(node, dict):
        return node

    provider_key = (provider or "").strip().lower()
    if provider_key == "gemini":
        drop_keys = _GEMINI_DROP_KEYS
    elif provider_key == "anthropic":
        drop_keys = _ANTHROPIC_DROP_KEYS
    else:
        drop_keys = _COMMON_DROP_KEYS

    out: Dict[str, Any] = {}
    for key, value in node.items():
        if key in drop_keys:
            continue
        if key == "const":
            out["enum"] = [value]
            continue
        if key == "type" and isinstance(value, list):
            non_null = [v for v in value if v != "null"]
            out["type"] = non_null[0] if len(non_null) == 1 else non_null
            continue
        out[key] = _clean_schema_for_provider_recursive(value, provider_key)

    for union_key in ("anyOf", "oneOf"):
        variants = out.get(union_key)
        if isinstance(variants, list):
            flattened = _flatten_literal_union(variants)
            if flattened:
                out.pop(union_key, None)
                for k, v in flattened.items():
                    out[k] = v

    return out


def normalize_tool_schema_for_provider(schema: Dict[str, Any], provider: str) -> Dict[str, Any]:
    """
    Normalize schema then apply provider-specific cleanup pass.
    """
    base = normalize_tool_schema(schema)
    provider_key = (provider or "").strip().lower()
    cleaned = _clean_schema_for_provider_recursive(base, provider_key)
    if not isinstance(cleaned, dict):
        return base
    if cleaned.get("type") != "object":
        cleaned["type"] = "object"
    cleaned.setdefault("properties", {})
    if "required" in cleaned and not isinstance(cleaned.get("required"), list):
        cleaned["required"] = []
    if provider_key != "gemini":
        cleaned.setdefault("additionalProperties", True)
    return cleaned


def normalize_openai_tools_for_provider(
    tools: List[Dict[str, Any]], provider: str
) -> List[Dict[str, Any]]:
    """
    Apply provider-aware schema cleanup to OpenAI-compatible tools payload.
    """
    out: List[Dict[str, Any]] = []
    for item in tools or []:
        if not isinstance(item, dict):
            continue
        fn = item.get("function")
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name", "")).strip()
        if not name:
            continue
        params = fn.get("parameters")
        if not isinstance(params, dict):
            params = {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(fn.get("description", "")).strip(),
                    "parameters": normalize_tool_schema_for_provider(params, provider),
                },
            }
        )
    return out
