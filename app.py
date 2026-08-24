"""Extension declaration, secrets, lifecycle hooks.

WHY BYOK (bring-your-own-key), SAME REASONING AS AWS / GitLab CI/CD / n8n
Connector. Azure lives inside the USER'S OWN tenant/subscription --
Imperal cannot and should not broker access to someone else's Azure
subscription centrally.

WHY tenant_id + client_id + client_secret + subscription_id (A CONNECTION
RECORD), NOT A SINGLE TOKEN.

Azure uses OAuth2 Client Credentials Flow against Azure AD (Entra ID): an
App Registration (Service Principal) with a Client Secret. The resulting
access token is scoped to https://management.azure.com/.default and
expires in ~1 hour -- azure_client.py caches it per-connection and
refreshes on expiry (this is deliberately built in from day one, per the
known portfolio bug #2356: client-credentials connectors that did NOT
cache access_token between calls). Subscription ID is stored alongside
the credentials because almost every ARM request needs it in the path.

WHY THIS CONNECTOR IS SCOPED TO VMs/Storage/SQL/Functions/Role
Assignments/Monitor/Cost Management, NOT "ALL OF AZURE".

Azure Resource Manager fronts hundreds of resource providers. Covering
all of them is neither possible nor useful in v1 -- this connector
mirrors AWS Connector's domain choice (compute, storage, managed DB,
serverless functions, IAM-equivalent, monitoring, cost) so the two
hyperscaler connectors read the same way to a user comparing clouds.
"""
from __future__ import annotations

from imperal_sdk import Extension, ChatExtension

ext = Extension(
    "azure-connector",
    version="0.1.0",
    display_name="Microsoft Azure",
    description=(
        "Connect your own Azure subscription (App Registration + Client "
        "Secret, OAuth2 client credentials) to see and manage Virtual "
        "Machines, Storage Accounts, Azure SQL Database, Function Apps, "
        "role assignments, Azure Monitor alerts, and Cost Management from "
        "Imperal. Your Service Principal is verified against your tenant "
        "before it's saved. Scoped to the operational core -- AKS, "
        "Cognitive Services and Azure DevOps are out of scope."
    ),
    icon="icon.svg",
    actions_explicit=True,
    capabilities=["azure:read", "azure:write"],
)

chat = ChatExtension(
    ext,
    tool_name="azure-connector",
    description="View and manage Azure -- VMs, Storage, SQL, Functions, roles, Monitor, Cost Management",
)

ext.secret(
    "azure_connections",
    (
        "Your connected Azure subscriptions -- stored as a JSON array, one "
        "entry per subscription, each with its own Tenant ID, Client ID, "
        "Client Secret, Subscription ID, and a friendly label. Managed "
        "through connect_azure / disconnect_azure -- you should not need "
        "to edit this directly."
    ),
    required=True,
    write_mode="both",
    max_bytes=65536,
    rotation_hint_days=90,
)(lambda: None)


@ext.health_check
async def health_check(ctx) -> dict:
    """Fast configuration health; no third-party call -- just confirms at
    least one Azure subscription connection is stored, same shape as AWS
    Connector's / GitLab CI/CD Connector's health_check."""
    import json as _json
    raw = await ctx.secrets.get("azure_connections")
    try:
        count = len(_json.loads(raw)) if raw else 0
    except Exception:
        count = 0
    return {
        "healthy": True,
        "detail": (
            f"{count} Azure subscription(s) connected." if count
            else "Not connected yet -- run connect_azure."
        ),
    }
