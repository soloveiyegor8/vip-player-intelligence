# Качество разбора: Ollama (локально) (gemma3:12b)

Оценено диалогов: 40 из 40

| Метрика | Значение |
|---|---|
| Полнота по критичным флагам (RG/комплаенс) | 100% (8/8) |
| Полнота по всем обязательным флагам | 74% (20/27) |
| Точность флагов (доля не ложных) | 80% (32/40) |
| Критичные диалоги помечены critical | 100% (8/8) |
| Ложные critical на некритичных диалогах | 0 из 25 |
| Итоговая оценка в допустимом диапазоне | 80% (32/40) |
| Тема диалога | 52% (21/40) |
| Решён ли вопрос | 81% (26/32) |
| Нужен ли ответ | 94% (30/32) |

## Расхождения

| Диалог | Пропущено | Лишнее | Оценка (ожидалось) |
|---|---|---|---|
| D001 | UNRESOLVED_PAYMENT | — | poor (poor/critical) |
| D002 | — | — | ok (good/excellent) |
| D005 | — | ISSUE_IGNORED | critical (critical) |
| D014 | — | GENERIC_OUTREACH | ok (good/excellent) |
| D016 | PROMISE_NOT_KEPT | — | poor (poor/critical) |
| D019 | CHURN_THREAT | — | poor (poor/critical) |
| D022 | — | GENERIC_OUTREACH | ok (good/excellent) |
| D024 | RUDE_TONE | PRESSURE_TACTICS | poor (critical/poor) |
| D025 | — | — | ok (good/excellent) |
| D027 | — | — | ok (good/excellent) |
| D028 | — | PASSED_THE_BUCK | poor (good/excellent/ok) |
| D029 | — | CHURN_THREAT | poor (poor/ok) |
| D031 | FEEDBACK_NOT_ESCALATED | GENERIC_OUTREACH | poor (ok/poor) |
| D035 | FEEDBACK_NOT_ESCALATED | PRESSURE_TACTICS | poor (ok/poor) |
| D036 | PRESSURE_TACTICS | — | poor (poor/critical) |
| D037 | — | — | ok (good/excellent) |
| D038 | — | — | ok (good/excellent) |
