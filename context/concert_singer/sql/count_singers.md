---
db_id: concert_singer
question: 有多少个歌手？
source: manual
---
SELECT COUNT(DISTINCT Singer_ID) FROM singer;
