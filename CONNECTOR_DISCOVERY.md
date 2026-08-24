# Microsoft Azure Connector — Discovery

**Дата:** 2026-08-24. **Vikunja task:** #2413 (BBW Imperal Apps).
**Категория:** Гипермасштабные облака (IaaS/PaaS), второе приложение
после AWS Connector (см. `Docs/session-notes/NEXT_12_CATEGORIES_RESEARCH.md`).

## 1. Что такое продукт

Microsoft Azure — гипермасштабная облачная платформа (~20-22% доли рынка,
Synergy/Canalys Q2'25). Управление ресурсами идёт через единый
**Azure Resource Manager (ARM) REST API** (`management.azure.com`) —
в отличие от AWS (сотни раздельных сервисных API), у Azure один
управляющий плоскостной API поверх множества "resource providers"
(Microsoft.Compute, Microsoft.Storage, Microsoft.Sql, Microsoft.Network,
Microsoft.CostManagement и т.д.), каждый со своей `api-version`.

## 2. Авторизация

**OAuth2 Client Credentials Flow через Azure AD (Microsoft Entra ID).**
Пользователь регистрирует "App Registration" в своём Entra ID tenant,
получает Client ID (Application ID) + Client Secret + Tenant ID, и
назначает Service Principal нужную RBAC-роль (Reader/Contributor) на
Subscription или Resource Group. Токен получается через:

```
POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
grant_type=client_credentials
client_id={client_id}
client_secret={client_secret}
scope=https://management.azure.com/.default
```

Токен живёт ~1 час — нужно кэшировать между вызовами и обновлять по
истечении (учесть известный портфельный баг #2356: client-credentials
коннекторы не кешировали access_token между вызовами — в этом
коннекторе кэш обязателен с первого дня, не постфактум-фикс).

**Subscription ID** — обязательный параметр почти для каждого запроса
(ресурсы существуют внутри подписки), аналогично AWS region/account.
Хранится в самой connection-записи, не глобально.

## 3. Домен покрытия v1 (по аналогии с AWS: EC2/S3/RDS/Lambda/IAM/CloudWatch/Cost)

| Azure сервис | Аналог в AWS Connector | REST API |
|---|---|---|
| Virtual Machines (Compute) | EC2 | `Microsoft.Compute/virtualMachines`, api-version 2024-07-01 |
| Storage Accounts + Blob Containers | S3 | `Microsoft.Storage/storageAccounts` + Blob REST (`<account>.blob.core.windows.net`) |
| Azure SQL Database / servers | RDS | `Microsoft.Sql/servers/databases`, api-version 2023-08-01 |
| Function Apps | Lambda | `Microsoft.Web/sites` (kind=functionapp), api-version 2023-12-01 |
| Entra ID Users/Roles (Microsoft Graph, read-only) | IAM | `graph.microsoft.com/v1.0/users`, `Microsoft.Authorization/roleAssignments` |
| Azure Monitor Alerts + Metrics | CloudWatch | `Microsoft.Insights/metricAlerts`, `Microsoft.Insights/metrics` |
| Cost Management (usage/forecast) | Cost Explorer | `Microsoft.CostManagement/query`, `Microsoft.CostManagement/forecast` |

Вне охвата v1: AKS (Kubernetes — контейнерная оркестрация, отдельная
кандидатская категория как у AWS EKS/ECS), Azure Front Door/CDN
(DNS/CDN — вне operational core), Cognitive Services/Azure AI, App
Service advanced deployment slots, Azure DevOps (отдельная категория —
уже есть GitLab CI/CD, аналогичный домен).

## 4. Формат ответов и протокол

Все ARM API — REST + **JSON** (в отличие от AWS EC2's Query/XML) —
существенно проще парсить, не нужен XML ElementTree слой, только
`json.loads`. Единый паттерн пагинации через `nextLink` в теле ответа.

## 5. Деньги — Decimal, не float()

Cost Management API возвращает суммы как числа в JSON — парсить через
`Decimal(str(...))`, не `float()` напрямую (см. APP_SAFETY_CHECKLIST.md
пункт про денежные суммы, тот же баг-паттерн уже исправлен в AWS
Connector's Cost Explorer handlers).

## 6. Риски безопасности (BYOK)

Service Principal может иметь Owner/Contributor права на всю подписку —
максимально высокий потенциальный риск, аналогично AWS Access Key.
На экране подключения — явная рекомендация назначить роль **Reader**
для базового read-only сценария, с мягким предупреждением (не
блокировкой), если diagnostic-проверка обнаружит Owner/Contributor.

## 7. Ярусы функционала

**Ярус 1 (MVP):** connect_azure (client credentials + subscription_id,
token caching), disconnect_azure, list_connections, list_virtual_machines,
get_virtual_machine, list_storage_accounts, list_sql_databases,
list_function_apps, list_resource_groups.

**Ярус 2:** start/stop/restart VM (Ярус 3 по риску — деструктивно),
invoke Function App, list Entra ID users (Graph API), list role
assignments, list Monitor metric alerts, get Monitor metrics.

**Ярус 3 (value-add + деструктивные):** get_cost_and_usage,
get_cost_forecast, get_cloud_overview (агрегированная сводка — VM
running/stopped, storage account count, SQL DB count, month-to-date
cost — прямой аналог AWS get_cloud_overview), start/stop/restart_vm с
подтверждением.

## 8. Источники

learn.microsoft.com/en-us/rest/api/resources/, learn.microsoft.com/en-us/rest/api/compute/,
learn.microsoft.com/en-us/rest/api/storagerp/, learn.microsoft.com/en-us/rest/api/cost-management/,
learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow,
learn.microsoft.com/en-us/graph/api/overview.
