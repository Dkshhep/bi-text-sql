---
db_id: academic
question: 返回 2000 年以后发表的论文标题。
source: cspider_train
---
```sql
SELECT title FROM publication WHERE year > 2000
```
