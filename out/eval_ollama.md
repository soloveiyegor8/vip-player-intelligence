# Качество разбора: Ollama (локально) (gemma3:12b)

Оценено диалогов: 40 из 40

| Метрика | Значение |
|---|---|
| Полнота по критичным флагам (RG/комплаенс) | 75% (6/8) |
| Полнота по всем обязательным флагам | 74% (20/27) |
| Точность флагов (доля не ложных) | 77% (34/44) |
| Критичные диалоги помечены critical | 88% (7/8) |
| Ложные critical на некритичных диалогах | 0 из 25 |
| Итоговая оценка в допустимом диапазоне | 70% (28/40) |
| Тема диалога | 50% (20/40) |
| Решён ли вопрос | 81% (26/32) |
| Нужен ли ответ | 94% (30/32) |

## Расхождения

| Диалог | Пропущено | Лишнее | Оценка (ожидалось) |
|---|---|---|---|
| D001 | UNRESOLVED_PAYMENT | RG_LOSS_CHASING_ENCOURAGED | critical (poor/critical) |
| D002 | — | — | ok (good/excellent) |
| D004 | — | — | ok (good/excellent) |
| D005 | RG_WITHDRAWAL_DISCOURAGED | ISSUE_IGNORED | poor (critical) |
| D009 | — | — | ok (good/excellent) |
| D012 | — | ISSUE_IGNORED | poor (poor/ok) |
| D014 | — | GENERIC_OUTREACH | ok (good/excellent) |
| D016 | PROMISE_NOT_KEPT | — | poor (poor/critical) |
| D019 | CHURN_THREAT | ISSUE_IGNORED | poor (poor/critical) |
| D022 | — | MISLEADING_INFO | ok (good/excellent) |
| D025 | — | — | ok (good/excellent) |
| D027 | — | — | ok (good/excellent) |
| D028 | — | PASSED_THE_BUCK | poor (good/excellent/ok) |
| D031 | FEEDBACK_NOT_ESCALATED | GENERIC_OUTREACH | poor (ok/poor) |
| D033 | RG_WITHDRAWAL_DISCOURAGED | — | critical (critical) |
| D035 | FEEDBACK_NOT_ESCALATED | — | poor (ok/poor) |
| D036 | — | RG_LOSS_CHASING_ENCOURAGED | critical (poor/critical) |
| D037 | — | — | ok (good/excellent) |
| D038 | — | PRESSURE_TACTICS | ok (good/excellent) |
| D039 | — | — | ok (good/excellent) |
