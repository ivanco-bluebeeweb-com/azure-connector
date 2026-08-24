# Azure Connector — идеальный первый запуск

Источник: `Docs/session-notes/ONBOARDING_FIRST_LAUNCH_STANDARD.md`.
Целевой пользователь: DevOps-инженер/облачный архитектор в компании на
стеке Microsoft.

## 1. Credential type

BYOK, максимально высокий риск: Tenant ID + Client ID + Client Secret
(App Registration в Entra ID) + Subscription ID. OAuth2 Client
Credentials Flow, access token кэшируется на ~1 час.

## 2. Идеальный флоу

1. **Первое открытие** — `Empty` с прямой ссылкой "Entra ID > App
   registrations > New registration" + явная рекомендация ПЕРЕД
   созданием секрета: "назначьте Service Principal роль Reader на
   вашей подписке — этого достаточно для начала работы".
2. **Форма** — Tenant ID, Client ID, Client Secret (password-type,
   никогда не отображается повторно), Subscription ID. Все четыре
   поля обязательны и с контекстными плейсхолдерами (например Tenant
   ID: "00000000-0000-0000-0000-000000000000").
3. **Диагностика при подключении** — получить access token через
   client credentials flow, затем лёгкий вызов
   `GET /subscriptions/{id}?api-version=2022-12-01` для проверки
   валидности связки + определения имени подписки и назначенной роли.
   Если роль Owner/Contributor — мягкое предупреждение, не блокировка.
4. **После успеха** — сводка "облачного здоровья": количество активных
   VM по статусам, расходы за текущий месяц (Cost Management), любые
   Function Apps с ошибками — сразу actionable, аналогично AWS
   Connector's Cloud Overview.
5. **Ошибка "AADSTS7000215" (invalid client secret)** — конкретное
   объяснение: "секрет введён неверно или истёк — проверьте срок
   действия секрета в Entra ID", а не глухая ошибка авторизации.
6. **Ошибка 403 "AuthorizationFailed"** — отличать от неверных
   credentials: "подключение верно, но у Service Principal нет прав на
   это действие — назначьте нужную RBAC-роль" вместо общего "доступ
   запрещён".
7. **Смена подписки** — если у Service Principal доступ к нескольким
   подпискам, переключатель Subscription живёт в самом интерфейсе
   (аналогично Azure Connector's region switch по образцу AWS).

## 3. Разница с реализацией сейчас

См. `UI_COMPONENT_PLAN.md` §0.
