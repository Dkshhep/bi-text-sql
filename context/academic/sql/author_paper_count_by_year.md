---
db_id: academic
question: 返回“李政道”每年发表的论文数量。
source: cspider_train
---
```sql
SELECT p.year, COUNT(DISTINCT p.pid) AS publication_count
FROM writes AS w
JOIN author AS a ON w.aid = a.aid
JOIN publication AS p ON w.pid = p.pid
WHERE a.name = '李政道'
GROUP BY p.year
```
