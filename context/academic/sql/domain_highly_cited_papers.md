---
db_id: academic
question: 返回“数据库”领域中引用超过 200 次的论文标题。
source: cspider_train
---
```sql
SELECT p.title
FROM domain AS d
JOIN domain_publication AS dp ON d.did = dp.did
JOIN publication AS p ON p.pid = dp.pid
WHERE d.name = '数据库' AND p.citation_num > 200
```
