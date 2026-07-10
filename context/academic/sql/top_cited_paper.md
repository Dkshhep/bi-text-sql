---
db_id: academic
question: 返回引用次数最多的论文标题。
source: cspider_train
---
```sql
SELECT title
FROM publication
ORDER BY citation_num DESC
LIMIT 1
```
