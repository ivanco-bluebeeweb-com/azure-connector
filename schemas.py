"""Pydantic params models + SDL entity contracts for Azure Connector.

All params models are module-scope (V17 federal invariant, same rule as
AWS Connector's / GitLab CI/CD Connector's schemas.py).
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from imperal_sdk import sdl


class NoParams(BaseModel):
    """Explicit empty params model -- V17 disallows untyped handlers."""
    pass


# ──────────────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────────────


class ConnectAzureParams(BaseModel):
    tenant_id: str = Field("", description="Your Azure AD (Entra ID) Tenant ID, e.g. 00000000-0000-0000-0000-000000000000.")
    client_id: str = Field("", description="Your App Registration's Client ID (Application ID).")
    client_secret: str = Field("", description="Your App Registration's Client Secret value -- shown only once by Azure when created.")
    subscription_id: str = Field("", description="The Azure Subscription ID this connection manages.")
    label: str = Field("", description="Optional friendly name for this Azure subscription connection.")


class ProviderConnection(sdl.Entity):
    id: str = ""
    title: str = ""
    connected: bool = False
    detail: str = ""
    subscription_id: str = ""
    tenant_id: str = ""


class ProviderConnectionList(sdl.Entity):
    connections: list[ProviderConnection] = []


class DisconnectAzureParams(BaseModel):
    connection_id: str = Field(..., description="The connection id to disconnect, from list_connections.")


class DeleteResult(sdl.Entity):
    deleted: bool = False
    id: str = ""


class ConnectionIdParams(BaseModel):
    connection_id: str = Field("", description="Which connected Azure subscription to use; omit to use the only/most recent one.")


# ──────────────────────────────────────────────────────────────────────────
# Cloud overview
# ──────────────────────────────────────────────────────────────────────────


class CloudOverview(sdl.Entity):
    vm_running: int = 0
    vm_stopped: int = 0
    storage_account_count: int = 0
    sql_database_count: int = 0
    function_app_error_count: int = 0
    month_to_date_cost: str = ""
    currency: str = ""
    cost_by_service: list[dict] = []


class GetCloudOverviewParams(ConnectionIdParams):
    pass


# ──────────────────────────────────────────────────────────────────────────
# Virtual Machines
# ──────────────────────────────────────────────────────────────────────────


class VirtualMachine(sdl.Entity):
    id: str = ""
    name: str = ""
    resource_group: str = ""
    location: str = ""
    vm_size: str = ""
    power_state: str = ""
    os_type: str = ""


class VirtualMachineList(sdl.Entity):
    machines: list[VirtualMachine] = []


class ListVirtualMachinesParams(ConnectionIdParams):
    power_state_filter: str = Field("", description="Filter by power state: running, stopped, deallocated. Empty = all.")


class VmResourceParams(ConnectionIdParams):
    resource_group: str = Field(..., description="The resource group the VM belongs to.")
    vm_name: str = Field(..., description="The virtual machine's name.")


class StopVmParams(VmResourceParams):
    deallocate: bool = Field(True, description="True = fully deallocate (stop billing for compute); False = just power off.")


class VmActionResult(sdl.Entity):
    vm_name: str = ""
    action: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Storage Accounts
# ──────────────────────────────────────────────────────────────────────────


class StorageAccount(sdl.Entity):
    id: str = ""
    name: str = ""
    resource_group: str = ""
    location: str = ""
    sku: str = ""
    kind: str = ""


class StorageAccountList(sdl.Entity):
    accounts: list[StorageAccount] = []


class ListStorageAccountsParams(ConnectionIdParams):
    pass


class StorageAccountResourceParams(ConnectionIdParams):
    resource_group: str = Field(..., description="The resource group the storage account belongs to.")
    account_name: str = Field(..., description="The storage account's name.")


class BlobContainer(sdl.Entity):
    name: str = ""
    public_access: str = ""


class BlobContainerList(sdl.Entity):
    containers: list[BlobContainer] = []


# ──────────────────────────────────────────────────────────────────────────
# Azure SQL Database
# ──────────────────────────────────────────────────────────────────────────


class SqlServer(sdl.Entity):
    id: str = ""
    name: str = ""
    resource_group: str = ""
    location: str = ""
    version: str = ""


class SqlServerList(sdl.Entity):
    servers: list[SqlServer] = []


class ListSqlServersParams(ConnectionIdParams):
    pass


class SqlDatabase(sdl.Entity):
    id: str = ""
    name: str = ""
    status: str = ""
    sku: str = ""


class SqlDatabaseList(sdl.Entity):
    databases: list[SqlDatabase] = []


class ListSqlDatabasesParams(ConnectionIdParams):
    resource_group: str = Field(..., description="The resource group the SQL server belongs to.")
    server_name: str = Field(..., description="The SQL server's name.")


# ──────────────────────────────────────────────────────────────────────────
# Function Apps
# ──────────────────────────────────────────────────────────────────────────


class FunctionApp(sdl.Entity):
    id: str = ""
    name: str = ""
    resource_group: str = ""
    location: str = ""
    state: str = ""
    default_hostname: str = ""


class FunctionAppList(sdl.Entity):
    apps: list[FunctionApp] = []


class ListFunctionAppsParams(ConnectionIdParams):
    pass


class FunctionAppResourceParams(ConnectionIdParams):
    resource_group: str = Field(..., description="The resource group the function app belongs to.")
    app_name: str = Field(..., description="The function app's name.")


class FunctionAppActionResult(sdl.Entity):
    app_name: str = ""
    action: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Role assignments (IAM equivalent, read-only)
# ──────────────────────────────────────────────────────────────────────────


class RoleAssignment(sdl.Entity):
    id: str = ""
    principal_id: str = ""
    role_definition_id: str = ""
    scope: str = ""


class RoleAssignmentList(sdl.Entity):
    assignments: list[RoleAssignment] = []


class ListRoleAssignmentsParams(ConnectionIdParams):
    pass


# ──────────────────────────────────────────────────────────────────────────
# Azure Monitor
# ──────────────────────────────────────────────────────────────────────────


class MetricAlert(sdl.Entity):
    id: str = ""
    name: str = ""
    severity: int = 0
    enabled: bool = False
    description: str = ""


class MetricAlertList(sdl.Entity):
    alerts: list[MetricAlert] = []


class ListMetricAlertsParams(ConnectionIdParams):
    pass


class GetResourceMetricsParams(ConnectionIdParams):
    resource_id: str = Field(..., description="Full Azure resource ID to read metrics for, e.g. /subscriptions/.../virtualMachines/my-vm.")
    metric_names: str = Field(..., description="Comma-separated metric names, e.g. 'Percentage CPU'.")
    timespan: str = Field(..., description="ISO 8601 interval, e.g. 2026-08-01T00:00:00Z/2026-08-24T00:00:00Z.")
    interval: str = Field("PT1H", description="ISO 8601 duration for datapoint granularity, e.g. PT1H (hourly).")


class ResourceMetricsResult(sdl.Entity):
    resource_id: str = ""
    values: list[dict] = []


# ──────────────────────────────────────────────────────────────────────────
# Cost Management
# ──────────────────────────────────────────────────────────────────────────


class CostQueryResult(sdl.Entity):
    total_cost: str = ""
    currency: str = ""
    rows: list[dict] = []


class QueryCostsParams(ConnectionIdParams):
    from_date: str = Field(..., description="Start date, YYYY-MM-DD.")
    to_date: str = Field(..., description="End date, YYYY-MM-DD.")
    granularity: str = Field("Daily", description="Daily or Monthly.")
    group_by_service: bool = Field(False, description="Group results by Azure service name.")


class CostForecastResult(sdl.Entity):
    forecast_cost: str = ""
    currency: str = ""


class GetCostForecastParams(ConnectionIdParams):
    from_date: str = Field(..., description="Start date, YYYY-MM-DD.")
    to_date: str = Field(..., description="End date, YYYY-MM-DD.")
