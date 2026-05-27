# Collared Triple Taper Stems Have Superior Biomechanical Characteristics in Compromised Bone

- **id**: `doi:10.1016/j.artd.2026.101997`
- **方向**: hip_implant
- **优先级**: High（pipeline 评分）
- **本次处理**: checked（PDF 下载失败：HTTP 302 重定向死循环，Elsevier 出版商页面，未走通 Unpaywall）
- **来源日期**: 2026-06-01（未来日期预印本）

## 复核结论

**方向归类**：正确。Collared triple taper stem 是骨水泥/非骨水泥髋柄设计的核心议题，
研究对象「compromised bone」即骨质疏松股骨，直接对应髋柄初始稳定性与应力屏蔽风险——
属 hip_implant 核心而非外围。

**优先级 High**：判定合理。理由：
1. 24 个合成骨质疏松股骨 + 四种假体设计 + 轴向/扭转循环加载，是机械学层面比较
   设计差异的标准强证据范式。
2. 「带颈圈」相对无颈圈在 compromised bone 的差异，直接对应临床早期下沉与翻修
   失败的主因，对方向研究有直接借鉴。
3. 旋转刚度 + 失效扭矩双指标，方法论上比单一 push-out 试验更可信。

**摘要质量**：现有 LLM 摘要结构完整（动机/方法/结果/验证四段都填了），方法描述
有数量（24 个）、加载模式（轴向 + 扭转循环）、结果给出方向（下沉最小 + 刚度/扭矩
显著优于）。无明显幻觉。唯一缺：未报告具体 p 值与具体下沉量 mm 数，但这是摘要
层级合理的省略。

**是否值得跟进**：是。下次 Zotero 同步时手动找 PDF（Elsevier 通常需要机构网代理），
重点关注：(a) 四种假体的几何差异是否可参数化；(b) 合成骨与真骨在循环载荷下的
代表性争议是否被讨论；(c) 颈圈接触面积/接触压力是否量化。

## 抓取失败说明

- 失败原因：`download_error: HTTP Error 302: ... infinite loop` —— Elsevier 域名
  反爬虫，Unpaywall 给的 best_oa_location 跳到登录墙。
- 不必重试：此期刊的 OA 副本通常不存在，靠机构访问。
- 不影响后续：harness 已记 attempts=1，后续 next 会先取其他论文。
