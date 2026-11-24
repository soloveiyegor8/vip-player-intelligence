# Качество разбора: Claude API (скрипт) (claude-opus-5-5)

Оценено диалогов: 40 из 40

| Метрика | Значение |
|---|---|
| Полнота по критичным флагам (RG/комплаенс) | 100% (8/8) |
| Полнота по всем обязательным флагам | 100% (27/27) |
| Точность флагов (доля не ложных) | 84% (59/70) |
| Критичные диалоги помечены critical | 100% (8/8) |
| Ложные critical на некритичных диалогах | 0 из 25 |
| Итоговая оценка в допустимом диапазоне | 100% (40/40) |
| Тема диалога | 100% (40/40) |
| Решён ли вопрос | 97% (31/32) |
| Нужен ли ответ | 100% (32/32) |

## Расхождения

| Диалог | Пропущено | Лишнее | Оценка (ожидалось) |
|---|---|---|---|
| D008 | — | ISSUE_IGNORED | critical (critical) |
| D012 | — | VAGUE_ANSWER | poor (poor/ok) |
| D013 | — | VAGUE_ANSWER | poor (poor/ok) |
| D019 | — | ISSUE_IGNORED | poor (poor/critical) |
| D020 | — | ISSUE_IGNORED, VAGUE_ANSWER | critical (critical) |
| D021 | — | PASSED_THE_BUCK | poor (poor) |
| D029 | — | ISSUE_IGNORED | poor (poor/ok) |
| D033 | — | ISSUE_IGNORED | critical (critical) |
| D035 | — | VAGUE_ANSWER | poor (ok/poor) |
| D040 | — | ISSUE_IGNORED | critical (critical) |
