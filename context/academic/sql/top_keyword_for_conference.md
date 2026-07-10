---
db_id: academic
question: 返回“VLDB”会议中论文数量最多的关键词。
source: cspider_train
---
```sql
SELECT k.keyword
FROM publication_keyword AS pk
JOIN keyword AS k ON pk.kid = k.kid
JOIN publication AS p ON p.pid = pk.pid
JOIN conference AS c ON p.cid = c.cid
WHERE c.name = 'VLDB'
GROUP BY k.kid, k.keyword
ORDER BY COUNT(DISTINCT p.pid) DESC
LIMIT 1
```
