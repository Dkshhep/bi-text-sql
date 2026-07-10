---
db_id: academic
question: 返回“PVLDB”所属的研究领域。
source: cspider_train
---
```sql
SELECT d.name
FROM domain AS d
JOIN domain_journal AS dj ON d.did = dj.did
JOIN journal AS j ON j.jid = dj.jid
WHERE j.name = 'PVLDB'
```
