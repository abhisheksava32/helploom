"""Widget business logic. Owner: backend-core.

Planned entry points:

    get_widget(organization) -> WidgetConfig
    update_widget(widget, data) -> WidgetConfig    (normalises allowed_origins with
                                                    core.origins.normalize_origin)
    rotate_site_key(widget) -> WidgetConfig
    resolve_public_widget(site_key, origin) -> WidgetConfig | None
        Returns the enabled widget only when origin is in its allowed_origins (or is
        http://localhost:* while DEBUG and WIDGET_ALLOW_LOCALHOST_IN_DEBUG are on).
    embed_snippet(widget) -> str
"""
