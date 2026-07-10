---
db_id: academic
question: 返回“北京理工大学”发表论文的总引用数。
source: cspider_train
---
```sql
SELECT SUM(p.citation_num) AS total_citations
FROM organization AS o
JOIN author AS a ON o.oid = a.oid
JOIN writes AS w ON w.aid = a.aid
JOIN publication AS p ON w.pid = p.pid
WHERE o.name = '北京理工大学'
```
