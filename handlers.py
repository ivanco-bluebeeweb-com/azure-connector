"""Chat functions for Azure Connector: connection management, Virtual
Machines, Storage Accounts, Azure SQL, Function Apps, role assignments,
Azure Monitor, Cost Management, and a cloud overview (Tier 3 value-add).
Built on azure_client.py / schemas.py, following the same shape as AWS
Connector's / GitLab CI/CD Connector's handlers.py.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

from imperal_sdk import ActionResult

import azure_client as az
from app import ext, chat
from schemas import (
    NoParams,
    ConnectAzureParams, ProviderConnection, ProviderConnectionList,
    DisconnectAzureParams, DeleteResult, ConnectionIdParams,
    GetCloudOverviewParams, CloudOverview,
    ListVirtualMachinesParams, VirtualMachine, VirtualMachineList,
    VmResourceParams, StopVmParams, VmActionResult,
    ListStorageAccountsParams, StorageAccount, StorageAccountList,
    StorageAccountResourceParams, BlobContainer, BlobContainerList,
    ListSqlServersParams, SqlServer, SqlServerList,
    ListSqlDatabasesParams, SqlDatabase, SqlDatabaseList,
    ListFunctionAppsParams, FunctionApp, FunctionAppList,
    FunctionAppResourceParams, FunctionAppActionResult,
    ListRoleAssignmentsParams, RoleAssignment, RoleAssignmentList,
    ListMetricAlertsParams, MetricAlert, MetricAlertList,
    GetResourceMetricsParams, ResourceMetricsResult,
    QueryCostsParams, CostQueryResult,
    GetCostForecastParams, CostForecastResult,
)

_SECRET_NAME = "azure_connections"


# ──────────────────────────────────────────────────────────────────────────
# Connection storage helpers -- one secret holding a JSON array of
# connection records, same precedent as AWS Connector / GitLab CI/CD
# Connector (ctx.secrets has no "one secret per id" primitive).
# ──────────────────────────────────────────────────────────────────────────

async def _load_connections(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_SECRET_NAME)
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


async def _save_connections(ctx, connections: list[dict]) -> None:
    await ctx.secrets.set(_SECRET_NAME, json.dumps(connections))


async def _find_connection(ctx, connection_id: str) -> dict | None:
    connections = await _load_connections(ctx)
    if not connection_id and len(connections) == 1:
        return connections[0]
    for c in connections:
        if c.get("id") == connection_id:
            return c
    return None


async def _resolve(ctx, connection_id: str) -> dict | None:
    return await _find_connection(ctx, connection_id)


def _creds(conn: dict) -> dict:
    return {
        "tenant_id": conn["tenant_id"],
        "client_id": conn["client_id"],
        "client_secret": conn["client_secret"],
        "subscription_id": conn["subscription_id"],
    }


def _err(prefix: str, e: "az.ProviderError") -> ActionResult:
    return ActionResult.error(f"{prefix}: {e.detail}", code=f"AZURE_HTTP_{e.status_code}")


def _no_connection() -> ActionResult:
    return ActionResult.error(
        "No Azure connection found. Connect an Azure subscription first.",
        code="AZURE_NO_CONNECTION",
    )


# ──────────────────────────────────────────────────────────────────────────
# Connection management
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "connect_azure",
    "Connect your own Azure subscription by saving an App Registration's "
    "Tenant ID + Client ID + Client Secret plus a Subscription ID, after "
    "checking they actually work via OAuth2 client credentials. A "
    "Reader-only RBAC role is strongly recommended for the Service "
    "Principal you create.",
    action_type="write",
    chain_callable=True,
    data_model=ProviderConnection,
    event="azure-connector.connect_azure",
    effects=["azure.provider.connected"],
)
async def connect_azure(ctx, params: ConnectAzureParams) -> ActionResult:
    """Connect your own Azure subscription by saving an App Registration's Tenant ID + Client ID + Client Secret plus a Subscription ID."""
    missing = [
        name for name, val in (
            ("Tenant ID", params.tenant_id), ("Client ID", params.client_id),
            ("Client Secret", params.client_secret), ("Subscription ID", params.subscription_id),
        ) if not val
    ]
    if missing:
        return ActionResult.error(
            f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} required.",
            code="AZURE_MISSING_CREDENTIALS",
        )
    creds = {
        "tenant_id": params.tenant_id, "client_id": params.client_id,
        "client_secret": params.client_secret, "subscription_id": params.subscription_id,
    }
    try:
        identity = await az.check_connection(ctx, creds)
    except az.ProviderError as e:
        return _err("Couldn't verify these Azure credentials", e)

    connection_id = str(uuid.uuid4())
    record = {
        "id": connection_id,
        "title": params.label or identity.get("subscription_name") or params.subscription_id,
        **creds,
    }
    connections = await _load_connections(ctx)
    connections.append(record)
    await _save_connections(ctx, connections)
    return ActionResult.success(
        ProviderConnection(
            id=connection_id, title=record["title"], connected=True,
            detail=identity.get("subscription_state", ""),
            subscription_id=params.subscription_id, tenant_id=params.tenant_id,
        ),
        summary=f"Azure subscription connected -- {record['title']}.",
        refresh_panels=["azure_connect", "azure_settings"],
    )


@chat.function(
    "disconnect_azure",
    "Disconnect an Azure subscription: deletes the saved Tenant ID/Client "
    "ID/Client Secret/Subscription ID. Nothing in Azure itself is "
    "changed; the App Registration remains until you delete it yourself "
    "in Entra ID.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="azure-connector.disconnect_azure",
    effects=["azure.provider.disconnected"],
)
async def disconnect_azure(ctx, params: DisconnectAzureParams) -> ActionResult:
    """Disconnect an Azure subscription: deletes the saved Tenant ID/Client ID/Client Secret/Subscription ID."""
    connections = await _load_connections(ctx)
    remaining = [c for c in connections if c.get("id") != params.connection_id]
    if len(remaining) == len(connections) and connections:
        return ActionResult.error("Connection not found.", code="AZURE_CONN_NOT_FOUND")
    await _save_connections(ctx, remaining)
    return ActionResult.success(
        DeleteResult(deleted=True, id=params.connection_id),
        summary="Azure subscription disconnected.",
        refresh_panels=["azure_connect", "azure_settings"],
    )


@chat.function(
    "list_connections",
    "List the connected Azure subscriptions.",
    action_type="read",
    chain_callable=True,
    data_model=ProviderConnectionList,
)
async def list_connections(ctx, params: NoParams) -> ActionResult:
    """List the connected Azure subscriptions."""
    connections = await _load_connections(ctx)
    items = [
        ProviderConnection(
            id=c.get("id", ""), title=c.get("title", ""), connected=True,
            subscription_id=c.get("subscription_id", ""), tenant_id=c.get("tenant_id", ""),
        )
        for c in connections
    ]
    return ActionResult.success(ProviderConnectionList(connections=items))


# ──────────────────────────────────────────────────────────────────────────
# Virtual Machines
# ──────────────────────────────────────────────────────────────────────────


def _vm_from_arm(item: dict) -> VirtualMachine:
    props = item.get("properties", {}) or {}
    instance_view = props.get("instanceView", {}) or {}
    power_state = ""
    for s in instance_view.get("statuses", []) or []:
        code = s.get("code", "")
        if code.startswith("PowerState/"):
            power_state = code.split("/", 1)[1]
    rg = ""
    id_str = item.get("id", "")
    parts = id_str.split("/")
    if "resourceGroups" in parts:
        rg = parts[parts.index("resourceGroups") + 1]
    return VirtualMachine(
        id=id_str, name=item.get("name", ""), resource_group=rg,
        location=item.get("location", ""), vm_size=(props.get("hardwareProfile", {}) or {}).get("vmSize", ""),
        power_state=power_state, os_type=(props.get("storageProfile", {}) or {}).get("osDisk", {}).get("osType", ""),
    )


@chat.function(
    "list_virtual_machines",
    "List Virtual Machines in the connected Azure subscription, optionally filtered by power state.",
    action_type="read",
    chain_callable=True,
    data_model=VirtualMachineList,
)
async def list_virtual_machines(ctx, params: ListVirtualMachinesParams) -> ActionResult:
    """List Virtual Machines in the connected Azure subscription, optionally filtered by power state."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.list_virtual_machines(ctx, _creds(conn))
    except az.ProviderError as e:
        return _err("Couldn't list virtual machines", e)
    items = [_vm_from_arm(v) for v in body.get("value", [])]
    if params.power_state_filter:
        items = [v for v in items if v.power_state.lower() == params.power_state_filter.lower()]
    return ActionResult.success(VirtualMachineList(machines=items))


@chat.function(
    "get_virtual_machine",
    "Read one Virtual Machine in full, including power state and OS/network details.",
    action_type="read",
    chain_callable=True,
    data_model=VirtualMachine,
)
async def get_virtual_machine(ctx, params: VmResourceParams) -> ActionResult:
    """Read one Virtual Machine in full, including power state and OS/network details."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.get_virtual_machine(ctx, _creds(conn), params.resource_group, params.vm_name)
    except az.ProviderError as e:
        return _err("Couldn't read that virtual machine", e)
    return ActionResult.success(_vm_from_arm(body))


@chat.function(
    "start_virtual_machine",
    "Start a stopped/deallocated Virtual Machine.",
    action_type="write",
    chain_callable=True,
    data_model=VmActionResult,
    event="azure-connector.start_vm",
    effects=["azure.vm.started"],
)
async def start_virtual_machine(ctx, params: VmResourceParams) -> ActionResult:
    """Start a stopped/deallocated Virtual Machine."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        await az.start_virtual_machine(ctx, _creds(conn), params.resource_group, params.vm_name)
    except az.ProviderError as e:
        return _err("Couldn't start that virtual machine", e)
    return ActionResult.success(
        VmActionResult(vm_name=params.vm_name, action="start"),
        summary=f"Starting virtual machine {params.vm_name}.",
    )


@chat.function(
    "stop_virtual_machine",
    "Stop (or fully deallocate) a running Virtual Machine.",
    action_type="write",
    chain_callable=True,
    data_model=VmActionResult,
    event="azure-connector.stop_vm",
    effects=["azure.vm.stopped"],
)
async def stop_virtual_machine(ctx, params: StopVmParams) -> ActionResult:
    """Stop (or fully deallocate) a running Virtual Machine."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        await az.stop_virtual_machine(ctx, _creds(conn), params.resource_group, params.vm_name, params.deallocate)
    except az.ProviderError as e:
        return _err("Couldn't stop that virtual machine", e)
    return ActionResult.success(
        {"vm_name": params.vm_name, "action": "deallocate" if params.deallocate else "stop"},
        summary=f"Stopping virtual machine {params.vm_name}.",
    )


@chat.function(
    "restart_virtual_machine",
    "Restart a Virtual Machine.",
    action_type="write",
    chain_callable=True,
    data_model=VmActionResult,
    event="azure-connector.restart_vm",
    effects=["azure.vm.restarted"],
)
async def restart_virtual_machine(ctx, params: VmResourceParams) -> ActionResult:
    """Restart a Virtual Machine."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        await az.restart_virtual_machine(ctx, _creds(conn), params.resource_group, params.vm_name)
    except az.ProviderError as e:
        return _err("Couldn't restart that virtual machine", e)
    return ActionResult.success(
        VmActionResult(vm_name=params.vm_name, action="restart"),
        summary=f"Restarting virtual machine {params.vm_name}.",
    )


# ──────────────────────────────────────────────────────────────────────────
# Storage Accounts
# ──────────────────────────────────────────────────────────────────────────


def _storage_from_arm(item: dict) -> StorageAccount:
    rg = ""
    parts = item.get("id", "").split("/")
    if "resourceGroups" in parts:
        rg = parts[parts.index("resourceGroups") + 1]
    return StorageAccount(
        id=item.get("id", ""), name=item.get("name", ""), resource_group=rg,
        location=item.get("location", ""), sku=(item.get("sku", {}) or {}).get("name", ""),
        kind=item.get("kind", ""),
    )


@chat.function(
    "list_storage_accounts",
    "List Storage Accounts in the connected Azure subscription.",
    action_type="read",
    chain_callable=True,
    data_model=StorageAccountList,
)
async def list_storage_accounts(ctx, params: ListStorageAccountsParams) -> ActionResult:
    """List Storage Accounts in the connected Azure subscription."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.list_storage_accounts(ctx, _creds(conn))
    except az.ProviderError as e:
        return _err("Couldn't list storage accounts", e)
    return ActionResult.success(StorageAccountList(accounts=[_storage_from_arm(a) for a in body.get("value", [])]))


@chat.function(
    "get_storage_account",
    "Read one Storage Account in full.",
    action_type="read",
    chain_callable=True,
    data_model=StorageAccount,
)
async def get_storage_account(ctx, params: StorageAccountResourceParams) -> ActionResult:
    """Read one Storage Account in full."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.get_storage_account(ctx, _creds(conn), params.resource_group, params.account_name)
    except az.ProviderError as e:
        return _err("Couldn't read that storage account", e)
    return ActionResult.success(_storage_from_arm(body))


@chat.function(
    "list_blob_containers",
    "List blob containers inside a Storage Account.",
    action_type="read",
    chain_callable=True,
    data_model=BlobContainerList,
)
async def list_blob_containers(ctx, params: StorageAccountResourceParams) -> ActionResult:
    """List blob containers inside a Storage Account."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.list_blob_containers(ctx, _creds(conn), params.resource_group, params.account_name)
    except az.ProviderError as e:
        return _err("Couldn't list blob containers", e)
    items = [
        BlobContainer(name=c.get("name", ""), public_access=(c.get("properties", {}) or {}).get("publicAccess", ""))
        for c in body.get("value", [])
    ]
    return ActionResult.success(BlobContainerList(containers=items))


# ──────────────────────────────────────────────────────────────────────────
# Azure SQL Database
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_sql_servers",
    "List Azure SQL logical servers in the connected subscription.",
    action_type="read",
    chain_callable=True,
    data_model=SqlServerList,
)
async def list_sql_servers(ctx, params: ListSqlServersParams) -> ActionResult:
    """List Azure SQL logical servers in the connected subscription."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.list_sql_servers(ctx, _creds(conn))
    except az.ProviderError as e:
        return _err("Couldn't list SQL servers", e)
    items = []
    for s in body.get("value", []):
        rg = ""
        parts = s.get("id", "").split("/")
        if "resourceGroups" in parts:
            rg = parts[parts.index("resourceGroups") + 1]
        items.append(SqlServer(
            id=s.get("id", ""), name=s.get("name", ""), resource_group=rg,
            location=s.get("location", ""), version=(s.get("properties", {}) or {}).get("version", ""),
        ))
    return ActionResult.success(SqlServerList(servers=items))


@chat.function(
    "list_sql_databases",
    "List databases hosted on one Azure SQL logical server.",
    action_type="read",
    chain_callable=True,
    data_model=SqlDatabaseList,
)
async def list_sql_databases(ctx, params: ListSqlDatabasesParams) -> ActionResult:
    """List databases hosted on one Azure SQL logical server."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.list_sql_databases(ctx, _creds(conn), params.resource_group, params.server_name)
    except az.ProviderError as e:
        return _err("Couldn't list SQL databases", e)
    items = [
        SqlDatabase(
            id=d.get("id", ""), name=d.get("name", ""),
            status=(d.get("properties", {}) or {}).get("status", ""),
            sku=(d.get("sku", {}) or {}).get("name", ""),
        )
        for d in body.get("value", [])
    ]
    return ActionResult.success(SqlDatabaseList(databases=items))


# ──────────────────────────────────────────────────────────────────────────
# Function Apps
# ──────────────────────────────────────────────────────────────────────────


def _func_from_arm(item: dict) -> FunctionApp:
    rg = ""
    parts = item.get("id", "").split("/")
    if "resourceGroups" in parts:
        rg = parts[parts.index("resourceGroups") + 1]
    props = item.get("properties", {}) or {}
    return FunctionApp(
        id=item.get("id", ""), name=item.get("name", ""), resource_group=rg,
        location=item.get("location", ""), state=props.get("state", ""),
        default_hostname=props.get("defaultHostName", ""),
    )


@chat.function(
    "list_function_apps",
    "List Function Apps in the connected Azure subscription.",
    action_type="read",
    chain_callable=True,
    data_model=FunctionAppList,
)
async def list_function_apps(ctx, params: ListFunctionAppsParams) -> ActionResult:
    """List Function Apps in the connected Azure subscription."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.list_function_apps(ctx, _creds(conn))
    except az.ProviderError as e:
        return _err("Couldn't list function apps", e)
    return ActionResult.success(FunctionAppList(apps=[_func_from_arm(a) for a in body.get("value", [])]))


@chat.function(
    "restart_function_app",
    "Restart a Function App.",
    action_type="write",
    chain_callable=True,
    data_model=FunctionAppActionResult,
    event="azure-connector.restart_function_app",
    effects=["azure.function_app.restarted"],
)
async def restart_function_app(ctx, params: FunctionAppResourceParams) -> ActionResult:
    """Restart a Function App."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        await az.restart_function_app(ctx, _creds(conn), params.resource_group, params.app_name)
    except az.ProviderError as e:
        return _err("Couldn't restart that function app", e)
    return ActionResult.success(
        FunctionAppActionResult(app_name=params.app_name, action="restart"),
        summary=f"Restarting function app {params.app_name}.",
    )


# ──────────────────────────────────────────────────────────────────────────
# Role assignments (IAM equivalent, read-only)
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_role_assignments",
    "List role assignments (who has what RBAC role) in the connected subscription.",
    action_type="read",
    chain_callable=True,
    data_model=RoleAssignmentList,
)
async def list_role_assignments(ctx, params: ListRoleAssignmentsParams) -> ActionResult:
    """List role assignments (who has what RBAC role) in the connected subscription."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.list_role_assignments(ctx, _creds(conn))
    except az.ProviderError as e:
        return _err("Couldn't list role assignments", e)
    items = [
        RoleAssignment(
            id=r.get("id", ""), principal_id=(r.get("properties", {}) or {}).get("principalId", ""),
            role_definition_id=(r.get("properties", {}) or {}).get("roleDefinitionId", ""),
            scope=(r.get("properties", {}) or {}).get("scope", ""),
        )
        for r in body.get("value", [])
    ]
    return ActionResult.success(RoleAssignmentList(assignments=items))


# ──────────────────────────────────────────────────────────────────────────
# Azure Monitor
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_metric_alerts",
    "List Azure Monitor metric alert rules configured in the connected subscription.",
    action_type="read",
    chain_callable=True,
    data_model=MetricAlertList,
)
async def list_metric_alerts(ctx, params: ListMetricAlertsParams) -> ActionResult:
    """List Azure Monitor metric alert rules configured in the connected subscription."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.list_metric_alerts(ctx, _creds(conn))
    except az.ProviderError as e:
        return _err("Couldn't list metric alerts", e)
    items = [
        MetricAlert(
            id=a.get("id", ""), name=a.get("name", ""),
            severity=(a.get("properties", {}) or {}).get("severity", 0),
            enabled=(a.get("properties", {}) or {}).get("enabled", False),
            description=(a.get("properties", {}) or {}).get("description", ""),
        )
        for a in body.get("value", [])
    ]
    return ActionResult.success(MetricAlertList(alerts=items))


@chat.function(
    "get_resource_metrics",
    "Read Azure Monitor metric datapoints for one resource over a time window.",
    action_type="read",
    chain_callable=True,
    data_model=ResourceMetricsResult,
)
async def get_resource_metrics(ctx, params: GetResourceMetricsParams) -> ActionResult:
    """Read Azure Monitor metric datapoints for one resource over a time window."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.get_resource_metrics(
            ctx, _creds(conn), params.resource_id, params.metric_names,
            params.timespan, params.interval,
        )
    except az.ProviderError as e:
        return _err("Couldn't read resource metrics", e)
    return ActionResult.success(ResourceMetricsResult(resource_id=params.resource_id, values=body.get("value", []) if isinstance(body, dict) else []))


# ──────────────────────────────────────────────────────────────────────────
# Cost Management
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "query_costs",
    "Read Azure cost data for the connected subscription over a time window, optionally grouped by service.",
    action_type="read",
    chain_callable=True,
    data_model=CostQueryResult,
)
async def query_costs(ctx, params: QueryCostsParams) -> ActionResult:
    """Read Azure cost data for the connected subscription over a time window, optionally grouped by service."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.query_costs(
            ctx, _creds(conn), params.from_date, params.to_date,
            params.granularity, params.group_by_service,
        )
    except az.ProviderError as e:
        return _err("Couldn't read Cost Management data", e)
    props = body.get("properties", {}) or {}
    columns = [c.get("name", "") for c in props.get("columns", [])]
    rows_raw = props.get("rows", []) or []
    rows = [dict(zip(columns, r)) for r in rows_raw]
    total = Decimal("0")
    cost_idx = columns.index("Cost") if "Cost" in columns else (columns.index("PreTaxCost") if "PreTaxCost" in columns else -1)
    currency = ""
    if "Currency" in columns:
        ci = columns.index("Currency")
        for r in rows_raw:
            if len(r) > ci:
                currency = str(r[ci])
                break
    if cost_idx >= 0:
        for r in rows_raw:
            if len(r) > cost_idx:
                total += Decimal(str(r[cost_idx] or 0))
    return ActionResult.success(CostQueryResult(
        total_cost=str(total.quantize(Decimal("0.01"))), currency=currency, rows=rows,
    ))


@chat.function(
    "get_cost_forecast",
    "Read Azure Cost Management's own forecast of upcoming spend for the connected subscription.",
    action_type="read",
    chain_callable=True,
    data_model=CostForecastResult,
)
async def get_cost_forecast(ctx, params: GetCostForecastParams) -> ActionResult:
    """Read Azure Cost Management's own forecast of upcoming spend for the connected subscription."""
    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    try:
        body = await az.get_cost_forecast(ctx, _creds(conn), params.from_date, params.to_date)
    except az.ProviderError as e:
        return _err("Couldn't read the Azure cost forecast", e)
    props = body.get("properties", {}) or {}
    columns = [c.get("name", "") for c in props.get("columns", [])]
    rows = props.get("rows", []) or []
    total = Decimal("0")
    currency = ""
    if "Cost" in columns:
        ci = columns.index("Cost")
        for r in rows:
            if len(r) > ci:
                total += Decimal(str(r[ci] or 0))
    if "Currency" in columns:
        ci = columns.index("Currency")
        for r in rows:
            if len(r) > ci:
                currency = str(r[ci])
                break
    return ActionResult.success(CostForecastResult(
        forecast_cost=str(total.quantize(Decimal("0.01"))), currency=currency,
    ))


# ──────────────────────────────────────────────────────────────────────────
# Overview (Tier 3 value-add)
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "get_cloud_overview",
    "Value-add report: one-glance Azure subscription health snapshot -- VM counts by power state, Storage Account count, SQL database count, Function App error count, and month-to-date cost.",
    action_type="read",
    chain_callable=True,
    data_model=CloudOverview,
)
async def get_cloud_overview(ctx, params: GetCloudOverviewParams) -> ActionResult:
    """Value-add report: one-glance Azure subscription health snapshot -- VM counts by power state, Storage Account count, SQL database count, Function App error count, and month-to-date cost."""
    import datetime as _dt

    conn = await _resolve(ctx, params.connection_id)
    if not conn:
        return _no_connection()
    vm_running = vm_stopped = storage_count = sql_count = func_error_count = 0
    month_cost = Decimal("0")
    currency = ""
    try:
        body = await az.list_virtual_machines(ctx, _creds(conn))
        for v in body.get("value", []):
            vm = _vm_from_arm(v)
            if vm.power_state == "running":
                vm_running += 1
            elif vm.power_state in ("stopped", "deallocated"):
                vm_stopped += 1
    except az.ProviderError:
        pass
    try:
        body = await az.list_storage_accounts(ctx, _creds(conn))
        storage_count = len(body.get("value", []))
    except az.ProviderError:
        pass
    try:
        body = await az.list_sql_servers(ctx, _creds(conn))
        for s in body.get("value", []):
            rg = ""
            parts = s.get("id", "").split("/")
            if "resourceGroups" in parts:
                rg = parts[parts.index("resourceGroups") + 1]
            try:
                db_body = await az.list_sql_databases(ctx, _creds(conn), rg, s.get("name", ""))
                sql_count += max(0, len(db_body.get("value", [])) - 1)  # exclude the built-in "master" db
            except az.ProviderError:
                pass
    except az.ProviderError:
        pass
    try:
        body = await az.list_function_apps(ctx, _creds(conn))
        func_error_count = sum(
            1 for a in body.get("value", [])
            if (a.get("properties", {}) or {}).get("state", "").lower() not in ("running", "")
        )
    except az.ProviderError:
        pass
    try:
        today = _dt.date.today()
        start = today.replace(day=1)
        body = await az.query_costs(ctx, _creds(conn), start.isoformat(), today.isoformat(), "Monthly", False)
        props = body.get("properties", {}) or {}
        columns = [c.get("name", "") for c in props.get("columns", [])]
        rows = props.get("rows", []) or []
        if "Cost" in columns:
            ci = columns.index("Cost")
            for r in rows:
                if len(r) > ci:
                    month_cost += Decimal(str(r[ci] or 0))
        if "Currency" in columns:
            ci = columns.index("Currency")
            for r in rows:
                if len(r) > ci:
                    currency = str(r[ci])
                    break
    except az.ProviderError:
        pass
    return ActionResult.success(CloudOverview(
        vm_running=vm_running, vm_stopped=vm_stopped, storage_account_count=storage_count,
        sql_database_count=sql_count, function_app_error_count=func_error_count,
        month_to_date_cost=str(month_cost.quantize(Decimal("0.01"))), currency=currency,
    ))
