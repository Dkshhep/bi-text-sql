## global

- 仅使用 academic schema 中存在的表和字段；论文、作者、机构、关键词和领域的唯一标识分别为 pid、aid、oid、kid、did。
- 统计论文、作者、机构或关键词数量时，跨关联表查询必须分别按 publication.pid、author.aid、organization.oid、keyword.kid 去重，避免多对多关系重复计数。
- publication.citation_num 是论文被引用次数；cite 是逐条引用关系。查询“引用次数”时，除非问题明确要求引用关系或引用方论文，否则使用 citation_num。
- cite.citing 是发出引用的论文，cite.cited 是被引用的论文；两列均关联 publication.pid，查询方向不可互换。
- publication.cid 与 publication.jid 分别关联会议和期刊；它们允许为空，未明确要求时不得假设论文同时属于会议和期刊。

## contextual

- 查询作者与论文、作者的发表会议或期刊、合作者时，通过 writes 连接 author 与 publication；合作者是同一 publication.pid 上的另一位作者。
- 查询论文主题关键词时，通过 publication_keyword 连接 publication 与 keyword；查询领域下的关键词使用 domain_keyword，而不是从论文关键词反推。
- 查询论文所属领域时，通过 domain_publication 连接 domain 与 publication；查询作者研究领域使用 domain_author。
- 按组织筛选作者或其论文时，使用 author.oid = organization.oid；组织字段 continent 表示源数据中的区域分类。
- 用户说“发表在某会议/期刊”时，分别通过 publication.cid = conference.cid 或 publication.jid = journal.jid 筛选；不要把会议名称与期刊名称混用。
- 按年趋势或年份过滤论文时，使用 publication.year；总引用趋势以 SUM(publication.citation_num) 按 publication.year 分组。
