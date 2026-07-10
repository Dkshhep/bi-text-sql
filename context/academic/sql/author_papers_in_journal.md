---
db_id: academic
question: 返回“李政道”在“PVLDB”上发表的论文。
source: cspider_train
---
```sql
SELECT p.title
FROM publication AS p
JOIN journal AS j ON p.jid = j.jid
JOIN writes AS w ON w.pid = p.pid
JOIN author AS a ON w.aid = a.aid
WHERE a.name = '李政道' AND j.name = 'PVLDB'
```
