# Архітектурні діаграми

Діаграми Спринту 3 (SCRUM-59):

- [Послідовність обміну даними](sequence-exchange.puml) — [PNG](sequence-exchange.png)
- [Послідовність публікації](sequence-publish.puml) — [PNG](sequence-publish.png)
- [Діаграма класів](class-diagram.puml) — [PNG](class-diagram.png)

Файли `.puml` — джерело істини. PNG відрендерено PlantUML 1.2026.9.

Діаграма обміну даними описує наскрізний flow епіка E7, який реалізує SCRUM-56
(Назар, DevOps). У межах SCRUM-59 це архітектурний артефакт і контракт для SCRUM-56/57,
а не дублювання реалізації. Exchange flow **не видаляється** з проєкту: він залишається
частиною E7 і має бути узгоджений з реалізацією SCRUM-56.

Діаграма класів — цільовий стан Спринту 3. Її треба фіналізувати після merge
SCRUM-54 (поля публікації), SCRUM-55 (`DatasetVersion` / анонімізація) і SCRUM-58
(чинність правової підстави). Статус звірки — у [diagram-consistency.md](diagram-consistency.md).
