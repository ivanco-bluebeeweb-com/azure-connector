"""Azure Resource Manager (ARM) REST API client -- OAuth2 client credentials
over ctx.http, with per-connection access-token caching.

WHY ONE BASE_URL (management.azure.com), UNLIKE AWS CONNECTOR.

Azure Resource Manager fronts every resource provider through a single
control plane host -- unlike AWS's per-service-per-region hosts, ARM
requests all go to https://management.azure.com/subscriptions/{id}/... ,
differing only by the resource provider path and its own api-version
query parameter. This makes the client much closer in shape to a normal
REST client than aws_client.py's per-service protocol handling.

WHY THE TOKEN IS CACHED HERE, NOT RE-FETCHED PER CALL.

Known portfolio bug (#2356): earlier client-credentials connectors did
not cache access_token between calls, hammering the token endpoint on
every single action. Azure AD tokens are valid for ~1 hour -- caching
per access_key_id-equivalent (here: tenant_id+client_id+subscription_id)
for the lifetime of one process, refreshing 60s before expiry, is the
correct behaviour from day one.
"""
from __future__ import annotations

import time
from typing import Any

MANAGEMENT_HOST = "https://management.azure.com"
LOGIN_HOST = "https://login.microsoftonline.com"

# Module-level token cache, keyed by (tenant_id, client_id). Fine for a
# single extension process; a stale token past its own expiry is always
# re-checked before use, so a cold cache or eviction is harmless.
_TOKEN_CACHE: dict[tuple[str, str], tuple[str, float]] = {}


class ProviderError(Exception):
    """Raised for any Azure ARM/Graph API call that fails, carrying a
    status_code and a human-readable detail so handlers can distinguish
    AADSTS (bad credentials) from AuthorizationFailed (valid credentials,
    insufficient RBAC role) from anything else -- same principle as
    aws_client.ProviderError distinguishing SignatureDoesNotMatch from
    AccessDenied."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Azure API error {status_code}: {detail}")


async def _get_access_token(ctx, tenant_id: str, client_id: str, client_secret: str) -> str:
    cache_key = (tenant_id, client_id)
    cached = _TOKEN_CACHE.get(cache_key)
    if cached and time.time() < cached[1] - 60:
        return cached[0]

    resp = await ctx.http.post(
        f"{LOGIN_HOST}/{tenant_id}/oauth2/v2.0/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://management.azure.com/.default",
        },
    )
    if resp.status_code >= 400:
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass
        error_code = body.get("error", "")
        error_desc = (body.get("error_description") or "").split("\r\n")[0]
        if error_code == "invalid_client" or "AADSTS7000215" in error_desc:
            raise ProviderError(
                401,
                "Azure AD rejected the Client Secret: it may be wrong, "
                "expired, or already rotated. Check the secret's expiry "
                "in Entra ID > App registrations > Certificates & secrets.",
            )
        if "AADSTS700016" in error_desc or "AADSTS90002" in error_desc:
            raise ProviderError(
                404,
                "Azure AD didn't recognise the Tenant ID or Client ID -- "
                "double-check both against your App Registration's Overview page.",
            )
        raise ProviderError(
            resp.status_code,
            f"Azure AD token request failed: {error_desc or error_code or 'unknown error'}.",
        )
    body = resp.json()
    token = body.get("access_token")
    if not token:
        raise ProviderError(502, "Azure AD token response did not contain an access_token.")
    expiry = time.time() + float(body.get("expires_in", 3600))
    _TOKEN_CACHE[cache_key] = (token, expiry)
    return token


def _check_status(resp, action: str) -> Any:
    if resp.status_code in (200, 201, 202, 204):
        if not resp.text:
            return {}
        try:
            return resp.json()
        except Exception:
            return {}
    try:
        body = resp.json()
    except Exception:
        body = {}
    err = body.get("error", {}) if isinstance(body, dict) else {}
    code = err.get("code", "")
    message = err.get("message", "")
    if resp.status_code in (401,):
        raise ProviderError(401, f"Azure rejected the access token while trying to {action}. Try reconnecting.")
    if resp.status_code == 403 or code == "AuthorizationFailed":
        raise ProviderError(
            403,
            f"Azure recognised your credentials for {action}, but the "
            "Service Principal's RBAC role doesn't allow this action."
            + (f" ({message})" if message else ""),
        )
    if resp.status_code == 404:
        raise ProviderError(404, f"Not found while trying to {action}.")
    if resp.status_code == 429:
        raise ProviderError(429, f"Azure throttled the request to {action}. Try again shortly.")
    if resp.status_code >= 500:
        raise ProviderError(resp.status_code, f"Azure's own service had a problem while trying to {action}.")
    raise ProviderError(
        resp.status_code,
        f"Unexpected response while trying to {action} (HTTP {resp.status_code})."
        + (f" {code}: {message}" if message else ""),
    )


async def _arm_request(
    ctx, *, method: str, creds: dict, path: str, api_version: str,
    query_params: dict | None = None, json_body: dict | None = None, action_label: str,
) -> Any:
    token = await _get_access_token(ctx, creds["tenant_id"], creds["client_id"], creds["client_secret"])
    params = {"api-version": api_version, **(query_params or {})}
    url = f"{MANAGEMENT_HOST}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    if method.upper() == "GET":
        resp = await ctx.http.get(url, headers=headers, params=params)
    elif method.upper() == "POST":
        resp = await ctx.http.post(url, headers=headers, params=params, json=json_body or {})
    else:
        resp = await ctx.http.request(method, url, headers=headers, params=params, json=json_body or {})
    return _check_status(resp, action_label)


async def check_connection(ctx, creds: dict) -> dict:
    """Lightest possible call to verify a Service Principal + Subscription
    ID combination is valid: read the subscription's own metadata (per
    IDEAL_ONBOARDING §2.3, mirroring AWS Connector's sts:GetCallerIdentity)."""
    body = await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}", api_version="2022-12-01",
        action_label="verify connection",
    )
    return {
        "subscription_name": body.get("displayName", ""),
        "subscription_state": body.get("state", ""),
        "tenant_id": body.get("tenantId", creds.get("tenant_id", "")),
    }


# ──────────────────────────────────────────────────────────────────────────
# Virtual Machines (Microsoft.Compute)
# ──────────────────────────────────────────────────────────────────────────

async def list_virtual_machines(ctx, creds: dict) -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/providers/Microsoft.Compute/virtualMachines",
        api_version="2024-07-01", action_label="list virtual machines",
    )


async def get_virtual_machine(ctx, creds: dict, resource_group: str, vm_name: str) -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_name}",
        api_version="2024-07-01", query_params={"$expand": "instanceView"},
        action_label="read virtual machine",
    )


async def start_virtual_machine(ctx, creds: dict, resource_group: str, vm_name: str) -> dict:
    return await _arm_request(
        ctx, method="POST", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_name}/start",
        api_version="2024-07-01", action_label="start virtual machine",
    )


async def stop_virtual_machine(ctx, creds: dict, resource_group: str, vm_name: str, deallocate: bool = True) -> dict:
    action = "deallocate" if deallocate else "powerOff"
    return await _arm_request(
        ctx, method="POST", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_name}/{action}",
        api_version="2024-07-01", action_label="stop virtual machine",
    )


async def restart_virtual_machine(ctx, creds: dict, resource_group: str, vm_name: str) -> dict:
    return await _arm_request(
        ctx, method="POST", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_name}/restart",
        api_version="2024-07-01", action_label="restart virtual machine",
    )


# ──────────────────────────────────────────────────────────────────────────
# Storage Accounts (Microsoft.Storage)
# ──────────────────────────────────────────────────────────────────────────

async def list_storage_accounts(ctx, creds: dict) -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/providers/Microsoft.Storage/storageAccounts",
        api_version="2023-05-01", action_label="list storage accounts",
    )


async def get_storage_account(ctx, creds: dict, resource_group: str, account_name: str) -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{account_name}",
        api_version="2023-05-01", action_label="read storage account",
    )


async def list_blob_containers(ctx, creds: dict, resource_group: str, account_name: str) -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{account_name}/blobServices/default/containers",
        api_version="2023-05-01", action_label="list blob containers",
    )


# ──────────────────────────────────────────────────────────────────────────
# Azure SQL Database (Microsoft.Sql)
# ──────────────────────────────────────────────────────────────────────────

async def list_sql_servers(ctx, creds: dict) -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/providers/Microsoft.Sql/servers",
        api_version="2023-08-01-preview", action_label="list SQL servers",
    )


async def list_sql_databases(ctx, creds: dict, resource_group: str, server_name: str) -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/resourceGroups/{resource_group}/providers/Microsoft.Sql/servers/{server_name}/databases",
        api_version="2023-08-01-preview", action_label="list SQL databases",
    )


# ──────────────────────────────────────────────────────────────────────────
# Function Apps (Microsoft.Web, functionapp kind)
# ──────────────────────────────────────────────────────────────────────────

async def list_function_apps(ctx, creds: dict) -> dict:
    body = await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/providers/Microsoft.Web/sites",
        api_version="2023-12-01", action_label="list function apps",
    )
    items = [s for s in body.get("value", []) if "functionapp" in (s.get("kind") or "")]
    return {"value": items}


async def get_function_app(ctx, creds: dict, resource_group: str, app_name: str) -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/resourceGroups/{resource_group}/providers/Microsoft.Web/sites/{app_name}",
        api_version="2023-12-01", action_label="read function app",
    )


async def restart_function_app(ctx, creds: dict, resource_group: str, app_name: str) -> dict:
    return await _arm_request(
        ctx, method="POST", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/resourceGroups/{resource_group}/providers/Microsoft.Web/sites/{app_name}/restart",
        api_version="2023-12-01", action_label="restart function app",
    )


# ──────────────────────────────────────────────────────────────────────────
# Role assignments (Microsoft.Authorization -- Entra ID / IAM equivalent, read-only)
# ──────────────────────────────────────────────────────────────────────────

async def list_role_assignments(ctx, creds: dict) -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/providers/Microsoft.Authorization/roleAssignments",
        api_version="2022-04-01", action_label="list role assignments",
    )


async def list_role_definitions(ctx, creds: dict) -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/providers/Microsoft.Authorization/roleDefinitions",
        api_version="2022-04-01", action_label="list role definitions",
    )


# ──────────────────────────────────────────────────────────────────────────
# Azure Monitor (Microsoft.Insights) -- alerts and metrics
# ──────────────────────────────────────────────────────────────────────────

async def list_metric_alerts(ctx, creds: dict) -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/providers/Microsoft.Insights/metricAlerts",
        api_version="2018-03-01", action_label="list metric alerts",
    )


async def get_resource_metrics(ctx, creds: dict, resource_id: str, metric_names: str, timespan: str, interval: str = "PT1H") -> dict:
    return await _arm_request(
        ctx, method="GET", creds=creds,
        path=f"{resource_id}/providers/Microsoft.Insights/metrics",
        api_version="2018-01-01",
        query_params={"metricnames": metric_names, "timespan": timespan, "interval": interval},
        action_label="read resource metrics",
    )


# ──────────────────────────────────────────────────────────────────────────
# Cost Management (Microsoft.CostManagement) -- money handled as Decimal
# by handlers.py, never float() (APP_SAFETY_CHECKLIST.md).
# ──────────────────────────────────────────────────────────────────────────

async def query_costs(ctx, creds: dict, from_date: str, to_date: str, granularity: str = "Daily", group_by_service: bool = False) -> dict:
    grouping = [{"type": "Dimension", "name": "ServiceName"}] if group_by_service else []
    body = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {"from": from_date, "to": to_date},
        "dataset": {
            "granularity": granularity,
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": grouping,
        },
    }
    return await _arm_request(
        ctx, method="POST", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/providers/Microsoft.CostManagement/query",
        api_version="2023-11-01", json_body=body, action_label="query cost management",
    )


async def get_cost_forecast(ctx, creds: dict, from_date: str, to_date: str) -> dict:
    body = {
        "type": "Usage",
        "timeframe": "Custom",
        "timePeriod": {"from": from_date, "to": to_date},
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
        },
    }
    return await _arm_request(
        ctx, method="POST", creds=creds,
        path=f"/subscriptions/{creds['subscription_id']}/providers/Microsoft.CostManagement/forecast",
        api_version="2023-11-01", json_body=body, action_label="read cost forecast",
    )
