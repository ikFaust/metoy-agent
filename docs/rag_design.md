# Metoy 科学小导师 RAG 设计

## 当前 MVP

当前版本使用轻量本地检索，不依赖付费 embedding 或向量数据库。

流程：

```text
data/edutoy/documents.jsonl
  -> LocalRetriever 读取为 Document
  -> 对 title/tags/content 做关键词和中文短语分词
  -> 根据学生问题、学段、知识点和约束拼出检索 query
  -> BM25 + tag bonus 排序
  -> 把 top documents 交给 Agent/GLM
  -> 生成知识讲解、教具清单或实验指导
```

每条知识都是一行 JSON：

```json
{
  "id": "edutoy_0001",
  "category": "manual",
  "level": "通用",
  "title": "平面镜成像演示仪说明书",
  "content": "用于观察平面镜成像特点...",
  "tags": ["平面镜", "成像", "光学", "教具"],
  "path": "本地原始资料路径",
  "source": "local_material"
}
```

## 这是不是 RAG

是 RAG 的轻量版本。

RAG 的核心不是必须使用向量数据库，而是：

1. 先从外部知识库检索相关资料。
2. 再把检索结果作为上下文交给大模型或规则生成器。
3. 让回答基于资料，而不是只靠模型记忆自由发挥。

当前版本的 retriever 是 BM25/关键词检索；开发者控制台会展示命中文档和 Agent 轨迹，因此可以看见系统到底用了哪些资料。

## 为什么先不用 embedding

- 不需要额外 API 成本。
- 当前知识库只有 192 条文档片段，关键词检索已经能跑通 MVP。
- 教具名、知识点、实验关键词非常明确，BM25 容易解释。
- 作业报告里可以清楚展示每条回答来自哪些资料。

## 教具目录为什么单独做工具

“你们有哪些教具？”不是开放问答，而是标准目录查询。如果直接交给大模型生成，模型可能编造不存在的产品。

所以系统单独设计了 Teaching Aid Catalog：

```text
catalog_query
  -> 只筛选 category = manual 的文档
  -> 返回本地说明书中的真实教具
  -> 质量校验检查是否存在编造教具
```

## 后续升级

后续可以加一层向量检索：

```text
documents.jsonl
  -> embedding model
  -> Chroma/FAISS vector store
  -> semantic search
  -> rerank with topic/tool rules
  -> GLM answer generation
```

推荐保留 BM25 和标签检索，形成 hybrid retrieval：

```text
BM25 keyword score
+ vector similarity score
+ teaching-aid category boost
+ source reliability score
= final retrieval score
```

这样既能搜到语义相关资料，也不会丢掉“平面镜成像演示仪”“数显式液体压强探究仪”这种精确教具名。
