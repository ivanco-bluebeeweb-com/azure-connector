"""The single "App settings" screen (center slot) -- connection management
(disconnect per Azure subscription) for Azure Connector. Split out of
panels.py per the same convention as AWS Connector's / GitLab CI/CD
Connector's panels_settings.py.

Per ~/UI_INTERFACE_STANDARD.md: the left sidebar never wraps the connect
form in a Card, and disconnect (never exposed in the sidebar itself) lives
here, one row per connected Azure subscription. The one secondary
"App settings" button sits LAST at the bottom of the sidebar.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers as h


def _connection_row(c: dict) -> ui.UINode:
    label = c.get("title") or c.get("subscription_id", "")
    return ui.Stack(direction="v", gap=1, align="start", children=[
        ui.Text(label, variant="body"),
        ui.Text(f"Subscription: {c.get('subscription_id', '')}", variant="caption"),
        ui.Text(f"Tenant: {c.get('tenant_id', '')}", variant="caption"),
        ui.Button(
            "Disconnect", variant="danger", size="sm",
            on_click=ui.Call("disconnect_azure", {"connection_id": c.get("id")}),
        ),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Stack(direction="v", gap=1, children=[
            ui.Text("Connections", variant="heading"),
            ui.Text("No Azure subscriptions connected yet.", variant="caption"),
        ])
    children: list[ui.UINode] = [ui.Text("Connections", variant="heading")]
    for i, c in enumerate(connections):
        if i:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, children=children)


@ext.panel("azure_settings", slot="center", title="Azure -- App settings", center_overlay=True)
async def azure_settings_panel(ctx, **kwargs) -> object:
    connections = await h._load_connections(ctx)
    return ui.Stack(direction="v", gap=4, children=[
        ui.Header(text="App settings", level=2, subtitle="Microsoft Azure"),
        _connections_section(connections),
        ui.Divider(),
        ui.Text(
            "Disconnecting removes the saved Tenant ID/Client ID/Client "
            "Secret from Imperal only. Nothing is changed in your Azure "
            "subscription -- delete or rotate the App Registration's "
            "secret yourself in Entra ID if you no longer want it to work "
            "at all.",
            variant="caption",
        ),
    ])
