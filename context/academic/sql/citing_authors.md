---
db_id: academic
question: 返回引用“李政道”论文的作者。
source: cspider_train
---
```sql
SELECT DISTINCT citing_author.name
FROM author AS cited_author
JOIN writes AS cited_writes ON cited_writes.aid = cited_author.aid
JOIN cite AS c ON c.cited = cited_writes.pid
JOIN writes AS citing_writes ON citing_writes.pid = c.citing
JOIN author AS citing_author ON citing_author.aid = citing_writes.aid
WHERE cited_author.name = '李政道'
```
