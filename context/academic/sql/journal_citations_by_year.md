---
db_id: academic
question: 返回“PVLDB”中每年的论文总引用数。
source: cspider_train
---
```sql
SELECT p.year, SUM(p.citation_num) AS total_citations
FROM publication AS p
JOIN journal AS j ON p.jid = j.jid
WHERE j.name = 'PVLDB'
GROUP BY p.year
```
