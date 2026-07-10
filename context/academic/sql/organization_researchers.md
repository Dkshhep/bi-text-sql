---
db_id: academic
question: 返回“北京理工大学”的所有研究人员。
source: cspider_train
---
```sql
SELECT a.name
FROM organization AS o
JOIN author AS a ON o.oid = a.oid
WHERE o.name = '北京理工大学'
```
