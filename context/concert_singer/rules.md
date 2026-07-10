## global
- 仅使用 concert_singer 数据库 schema 中存在的表和字段。
- 统计歌手数量时优先使用 singer.Singer_ID 去重。

## contextual
- 分析歌手参加演唱会时，优先通过 singer_in_concert 关联 singer 与 concert。
- 用户询问演唱会年份趋势时，默认使用 concert.Year 作为时间字段。
