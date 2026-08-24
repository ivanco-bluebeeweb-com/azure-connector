# Azure Connector — UI component plan

Источники: `Docs/session-notes/UI_COMPONENT_VOCABULARY.md`, `UI_INTERFACE_STANDARD.md`,
`concepts/panels.md`. Основано на `IDEAL_ONBOARDING.md` и `PREPARATION.md` этого приложения.

## 0. Разница с реализацией сейчас

Приложение ещё не реализовано (Фаза 1 discovery/preparation только что
завершена) — этот план описывает целевой интерфейс, который строится
сразу вместе с кодом Яруса 1, а не добавляется после.

## 1. Компоненты

| Экран | Примитивы | Почему именно эти |
|---|---|---|
| Sidebar (left) | `Stack`(direction="v", align="start") + `Text`(имя подписки) + `Select`(subscription_switch, если несколько) + `Divider` + navigation `ListItem`(VMs/Storage/SQL/Functions/Entra ID/Monitor/Cost) + `Button`("App settings") | Без карточек по стандарту. Subscription-select живёт в сайдбаре, аналогично region-select у AWS Connector. |
| Cloud Overview (center, `center_overlay=True`) | `Stats`(children=[VM running/stopped, Storage accounts, SQL databases, Function Apps with errors 24h]) + `Chart`(type="bar", месячные расходы по сервисам — Cost Management) | Первый экран после подключения — сразу actionable сводка, как требует IDEAL_ONBOARDING §2.4, прямой аналог AWS Cloud Overview. |
| Virtual Machines | `Select`(power_state_filter: running/stopped/deallocated) + `DataTable`(columns=[name, vm_size, power_state Badge, resource_group, location]; sortable) | Табличный список ресурсов — стандартный паттерн портфеля. |
| VM Detail | Back-button + `KeyValue`(items=[OS type, VM size, OS disk, network interfaces, tags]) + `Stack`(direction="h", children=[Button("Stop"), Button("Start"), Button("Restart")]) — Ярус 3, за confirm-модалкой | Деструктивные операции — отдельная кнопка с подтверждением, не auto-execute (PREPARATION §4). |
| Storage Accounts | `DataTable`(columns=[name, resource_group, location, sku, kind]; sortable) | Простой список, аналогично AWS S3 Buckets. |
| Storage Account Detail (Blob Containers) | Back-button + `DataTable`(columns=[container_name, public_access, last_modified]; sortable) | Список контейнеров — уровень ниже bucket-листинга AWS. |
| SQL Databases | `DataTable`(columns=[database_name, server_name, status Badge, tier, max_size_gb]; sortable) | Тот же табличный паттерн, аналог AWS RDS. |
| Function Apps | `DataTable`(columns=[name, runtime_stack, state Badge, error_count_24h Badge]; sortable) + row action "View Logs" | Ошибки за 24ч — сразу видимый Badge, аналог AWS Lambda. |
| Function App Detail | Back-button + `KeyValue`(items=[runtime, plan, region]) + `Code`(последний лог, read-only) + `Button`("Invoke") | `Code` примитив — то, чем показывать сырой лог-вывод, аналогично AWS Lambda Detail. |
| Entra ID Users/Roles | `Tabs`(items=["Users", "Role assignments"]) + `DataTable`(columns=[display_name/role_name, principal_type, scope]; sortable) | Две связанные, но разные сущности; `Tabs` разводит их без потери контекста, аналог AWS IAM Users/Roles. |
| Monitor Alerts | `DataTable`(columns=[alert_name, severity Badge, enabled Badge, target_resource]; sortable) | Состояние алертов — тот же паттерн Badge-колонки, аналог AWS CloudWatch Alarms. |
| Cost Management | `Select`(period: MTD/last_month/last_3_months) + `Chart`(type="bar", по сервисам) + `Chart`(type="line", тренд по дням) + `Stats`(children=[total_cost, forecast]) | Расходы — единственный экран с двумя диаграммами, аналог AWS Cost Explorer. |
| Empty states | `Empty`(message + иконка) — до первого подключения и при пустых списках ресурсов в подписке | Каноничный `Empty`, не кастомный текст. |
| App settings | `Form`(children=[subscription select, tenant/client ID read-only, disconnect Button]) | Единственное место с инструкцией по управлению подключением — не дублируется в сайдбаре. |

## 2. Формы — обязательные требования (UI_INTERFACE_STANDARD)

- Все инпуты — с лейблами, плейсхолдер контекстно-подходящий (например
  для Tenant ID: `"00000000-0000-0000-0000-000000000000"`, для Client
  Secret: `"вставьте секрет из Entra ID"`).
- Контейнер формы подключения растянут на всю ширину левого сайдбара;
  содержимое растянуто внутри себя на всю ширину контейнера.
- Инструкция по кнопке подключения — только в модалке/тултипе кнопки,
  не дублируется отдельным текстом в сайдбаре.
- `ui.Stats` принимает `children`/`columns`, НЕ `stats=` (известная
  ошибка валидатора деплоя, исправленная в AWS Connector — не повторять
  здесь с первого дня).

## 3. Навигация между экранами

`Sidebar ListItem` → меняет активный домен (VMs/Storage/SQL/Functions/
Entra ID/Monitor/Cost) → центральная панель рендерит соответствующий
`DataTable`/`Stats`/`Chart` экран. Detail-экраны открываются кликом по
строке `DataTable`, с явной кнопкой "Назад" (Back-button паттерн,
использован во всех detail-экранах портфеля, включая AWS Connector).
