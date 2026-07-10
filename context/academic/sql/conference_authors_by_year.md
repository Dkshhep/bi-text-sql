---
db_id: academic
question: 返回 2010 年以后在“PVLDB”发表过论文的作者。
source: cspider_train
---
```sql
SELECT DISTINCT a.name
FROM publication AS p
JOIN journal AS j ON p.jid = j.jid
JOIN writes AS w ON w.pid = p.pid
JOIN author AS a ON w.aid = a.aid
WHERE j.name = 'PVLDB' AND p.year > 2010
```
