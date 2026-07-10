---
db_id: academic
question: 返回包含“自然语言”关键词的论文标题。
source: cspider_train
---
```sql
SELECT DISTINCT p.title
FROM publication_keyword AS pk
JOIN keyword AS k ON pk.kid = k.kid
JOIN publication AS p ON p.pid = pk.pid
WHERE k.keyword = '自然语言'
```
