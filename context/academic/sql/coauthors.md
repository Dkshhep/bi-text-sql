---
db_id: academic
question: 返回与“李政道”合作的作者。
source: cspider_train
---
```sql
SELECT DISTINCT coauthor.name
FROM writes AS target_writes
JOIN author AS target_author ON target_writes.aid = target_author.aid
JOIN writes AS coauthor_writes ON coauthor_writes.pid = target_writes.pid
JOIN author AS coauthor ON coauthor_writes.aid = coauthor.aid
WHERE target_author.name = '李政道'
  AND coauthor.aid <> target_author.aid
```
