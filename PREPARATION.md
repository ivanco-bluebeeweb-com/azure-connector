# Microsoft Azure Connector — Preparation

**Статус:** Фаза 1 (Discovery + архитектурные решения) завершена.
Объём релиза — максимум (Ярус 1+2+3), явно заявлен пользователем,
по прецеденту AWS/GitLab CI/CD/MuleSoft/Automation Anywhere/UiPath.

**Владелец продукта:** vlad@bluebeeweb.com
**Дата подготовки:** 2026-08-24, v0.1
**Vikunja task:** #2413 (BBW Imperal Apps), [App Development].

**Почему сейчас:** Azure — второй по доле рынка гипермасштабный
облачный провайдер (~20-22%, Synergy/Canalys Q2'25), стандарт для
компаний на Microsoft 365/AD — второе приложение категории
"Гипермасштабные облака (IaaS/PaaS)" из
`Docs/session-notes/NEXT_12_CATEGORIES_RESEARCH.md`.

---

## 1. Паспорт приложения

**Название в Marketplace (display_name): «Microsoft Azure»**.
Внутренний app_id/папка: `azure-connector`.

**Azure Connector** — коннектор к Azure Resource Manager (ARM) REST API
через OAuth2 Client Credentials Flow (Azure AD / Entra ID). BYOK:
пользователь подключает свою собственную App Registration (Client ID +
Client Secret + Tenant ID) + Subscription ID к своей собственной Azure
подписке.

**Сознательно вне охвата в v1:** AKS (контейнерная оркестрация —
отдельная кандидатская категория), Azure Front Door/CDN, Cognitive
Services/Azure AI, App Service advanced deployment slots, Azure DevOps
(уже покрыто GitLab CI/CD по домену). Домен v1: Virtual Machines,
Storage Accounts, Azure SQL Database, Function Apps, Entra ID
users/roles (read-only через Graph), Azure Monitor (alerts/metrics),
Cost Management.

## 2. Проблема в человеческих словах

Когда **DevOps-инженер или облачный архитектор в компании на стеке
Microsoft** сталкивается с необходимостью **быстро проверить состояние
виртуальных машин, хранилищ или расходов через естественный язык**, ему
приходится **вручную заходить в Azure Portal, искать нужную подписку и
resource group**, из-за чего возникают **потеря времени на навигацию и
невозможность получить агрегированный ответ (например "сколько мы
тратим на VM в этом месяце") без открытия Cost Management отдельно**.

## 3. Целевой пользователь

DevOps/SRE-инженер, облачный архитектор в компании, использующей Azure
как основную (или одну из) облачных платформ, часто вместе с Microsoft
365/Entra ID для identity management. Вторичная аудитория — FinOps/CTO,
которому нужен агрегированный отчёт по расходам.

## 4. Границы данных и разрешения (Azure RBAC)

BYOK с максимально высоким потенциальным риском (Service Principal
может иметь Owner/Contributor права на всю подписку). Auth & Credentials
Standard применяется в самой строгой форме:

- На экране подключения — явная рекомендация назначить Service
  Principal роль **Reader** на уровне Subscription для базового
  read-only сценария.
- Явное мягкое предупреждение (не блокировка), если diagnostic-проверка
  (`GET /subscriptions/{id}?api-version=2022-12-01`) показывает, что
  Service Principal имеет Owner/Contributor роль.
- Деструктивные операции (stop/restart VM, отзыв ролей) — Ярус 3,
  требуют явного подтверждения на уровне UI, не auto-execute.

## 5. Subscription ID и Tenant ID — обязательные параметры

Аналогично AWS region — почти каждый запрос идёт через
`/subscriptions/{subscription_id}/...`. Форма подключения обязана
спрашивать Tenant ID, Client ID, Client Secret, и Subscription ID (все
четыре обязательны для client credentials flow + ARM-запросов).

## 6. Токен-кэширование — критично с первого дня

OAuth2 access token живёт ~1 час. Портфельный баг #2356 (client-
credentials коннекторы не кешируют access_token между вызовами) должен
быть учтён здесь ИЗНАЧАЛЬНО: клиент кэширует токен в памяти контекста
запроса вместе с его `expires_in`, не запрашивает новый на каждый вызов.
