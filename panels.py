"""Panel UI -- connections list/connect form for Azure Connector.

SIDEBAR CONTENT -- NO CARDS ANYWHERE, per ~/UI_INTERFACE_STANDARD.md's
"left sidebar, no decorated cards" rule (same convention as AWS
Connector's / GitLab CI/CD Connector's panels.py).

Every section (connections, connect form) is a plain ui.Stack, content
stacked vertically and left-aligned, sections separated by ui.Divider() --
no Card border/background/shadow anywhere in this slot. Disconnect lives
only in the "App settings" screen (panels_settings.py). The one secondary
"App settings" button is always the LAST element at the bottom of the
sidebar.

WHY A FULL FORM (tenant id + client id + client secret + subscription id),
NOT A SINGLE TOKEN, UNLIKE MOST OF THE PORTFOLIO.

Azure has no single bearer token for BYOK -- an OAuth2 client-credentials
exchange needs all three App Registration identifiers plus the
Subscription ID that scopes almost every request (see azure_client.py).
The form asks for all four explicitly.

Per Vlad's standing rule: every input carries its own label (not just a
placeholder), placeholders are contextually specific, and the form
container is stretched to the full width of the left sidebar with its
contents stretched to fill it. The sidebar carries NO instructions that
duplicate the "How do I set this up?" modal.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers as h


def _settings_button() -> ui.UINode:
    """The one required secondary entry point into the settings screen --
    always the last element at the bottom of the sidebar."""
    return ui.Button(
        "App settings", variant="secondary", size="sm", full_width=True,
        icon="settings", on_click=ui.Call("__panel__azure_settings"),
    )


def _connection_row(c: dict) -> ui.UINode:
    return ui.Stack(direction="v", gap=1, children=[
        ui.Text(c.get("title") or c.get("subscription_id", ""), variant="body"),
        ui.Text(f"Subscription: {c.get('subscription_id', '')}", variant="caption"),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Text("No Azure subscriptions connected yet.", variant="caption")
    children: list[ui.UINode] = []
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, children=children)


def _connect_section() -> ui.UINode:
    """Plain content, no Card wrapper. Stretched full-width per
    UI_INTERFACE_STANDARD.md. No intro heading/description text here --
    the App Registration walkthrough and Reader-role recommendation live
    ONLY in azure_connect_help's modal (button below opens it); repeating
    it here would duplicate that instruction."""
    return ui.Stack(direction="v", gap=3, align="stretch", children=[
        ui.Button("How do I set this up?", variant="ghost", size="sm",
                  icon="HelpCircle",
                  on_click=ui.Call("__panel__azure_connect_help")),
        ui.Form(
            action="connect_azure",
            submit_label="Verify and connect",
            children=[
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Tenant ID", variant="caption"),
                    ui.Input(param_name="tenant_id",
                             placeholder="00000000-0000-0000-0000-000000000000"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Client ID (Application ID)", variant="caption"),
                    ui.Input(param_name="client_id",
                             placeholder="Your App Registration's Application (client) ID"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Client Secret", variant="caption"),
                    ui.Password(param_name="client_secret",
                                 placeholder="Paste the secret value shown once by Azure"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Subscription ID", variant="caption"),
                    ui.Input(param_name="subscription_id",
                             placeholder="The subscription this Service Principal can access"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Label (optional)", variant="caption"),
                    ui.Input(param_name="label", placeholder="e.g. Production subscription"),
                ]),
            ],
        ),
    ])


@ext.panel("azure_connect", slot="left", title="Azure", icon="☁️",
           default_width=320, min_width=260, max_width=420)
async def azure_connect_panel(ctx, **kwargs) -> object:
    connections = await h._load_connections(ctx)
    connected = bool(connections)

    header = ui.Header(text="Microsoft Azure", level=2,
                        subtitle="Manage your VMs, Storage, SQL, Function Apps, roles and Cost Management from Imperal")

    if not connected:
        return ui.Stack(direction="v", gap=4, align="stretch", children=[
            header,
            _connect_section(),
            ui.Divider(),
            _settings_button(),
        ])

    return ui.Stack(direction="v", gap=4, align="stretch", children=[
        header,
        ui.Text("Connected subscriptions", variant="subtitle"),
        _connections_section(connections),
        ui.Divider(),
        ui.Button("Open cloud overview", variant="primary", size="sm", full_width=True,
                  icon="Cloud", on_click=ui.Call("__panel__azure_center")),
        ui.Divider(),
        _connect_section(),
        ui.Divider(),
        _settings_button(),
    ])


@ext.panel("azure_connect_help", slot="center",
           title="How to connect Azure", center_overlay=True)
async def azure_connect_help(ctx, **kwargs) -> object:
    content = ui.Stack(direction="v", gap=3, children=[
        ui.Text("1. Sign in to the Azure Portal and open Microsoft Entra ID > App registrations."),
        ui.Text("2. Click \"New registration\", give it a name, and register it -- copy the "
                "Application (client) ID and Directory (tenant) ID from its Overview page."),
        ui.Text("3. Open Certificates & secrets > New client secret, and copy the secret's "
                "Value immediately -- Azure shows it only once."),
        ui.Text("4. Open your Subscription > Access control (IAM) > Add role assignment, and "
                "assign the Reader role to this App Registration -- this is enough to start "
                "exploring your subscription safely."),
        ui.Text("5. Paste the Tenant ID, Client ID, Client Secret and Subscription ID into the "
                "form and Verify and connect."),
        ui.Divider(),
        ui.Alert(
            title="Scope your Service Principal before connecting",
            message=(
                "We strongly recommend assigning only the Reader role for your first "
                "connection. Broader roles (Contributor/Owner) work too, but a "
                "mis-scoped role can affect real infrastructure -- start read-only and "
                "widen permissions only when you need to act."
            ),
            type="warning",
        ),
        ui.Divider(),
        ui.Alert(
            title="Covers the operational core, not every Azure service",
            message=(
                "This connects Virtual Machines, Storage Accounts, Azure SQL Database, "
                "Function Apps, role assignments, Azure Monitor and Cost Management. "
                "AKS (container orchestration), Cognitive Services/Azure AI and Azure "
                "DevOps are out of scope here."
            ),
            type="info",
        ),
        ui.Divider(),
        ui.Link(
            label="Open Azure's official App Registration guide",
            href="https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app",
        ),
    ])
    return ui.Dialog(
        title="How to connect Azure",
        content=content,
        confirm_label="",
        cancel_label="Close",
    )


@ext.panel("azure_center", slot="center", title="Azure", icon="☁️", center_overlay=True)
async def azure_center_panel(ctx, connection_id: str = "", **kwargs) -> object:
    """Post-connect main screen: the cloud-health overview (Tier 3
    value-add) -- VM/Storage/SQL counts plus month-to-date cost, the same
    "actionable summary, not just a list" shape as AWS Connector's cloud
    overview."""
    connections = await h._load_connections(ctx)
    if not connections:
        return ui.Empty(
            message="Connect an Azure subscription from the sidebar to see your cloud overview here.",
            icon="☁️",
        )
    return await _cloud_overview(ctx, connection_id)


async def _cloud_overview(ctx, connection_id: str) -> ui.UINode:
    from schemas import GetCloudOverviewParams
    result = await h.get_cloud_overview(ctx, GetCloudOverviewParams(connection_id=connection_id))
    if not result.success or not result.data:
        return ui.Stack(direction="v", gap=3, align="stretch", children=[
            ui.Alert(title="Could not load your cloud overview",
                     message=result.error or "Check your connection and try again.",
                     type="error"),
        ])
    r = result.data
    return ui.Stack(direction="v", gap=3, align="stretch", children=[
        ui.Stats(children=[
            ui.Stat(label="VMs running", value=str(r.vm_running)),
            ui.Stat(label="VMs stopped", value=str(r.vm_stopped)),
            ui.Stat(label="Storage accounts", value=str(r.storage_account_count)),
            ui.Stat(label="SQL databases", value=str(r.sql_database_count)),
            ui.Stat(label="Function App errors (24h)", value=str(r.function_app_error_count)),
        ]),
        ui.Divider(),
        ui.Stat(label=f"Month-to-date cost ({r.currency or 'n/a'})", value=r.month_to_date_cost),
    ])
