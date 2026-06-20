# FutureMajor Agent RAG 设计

## 当前 MVP

当前版本使用轻量本地检索，不依赖付费 embedding。

流程：

```text
data/processed/knowledge.jsonl
  -> LocalRetriever 读取为 Document
  -> 对 title/tags/content 做分词
  -> 根据用户画像拼出检索 query
  -> BM25 + tag bonus 排序
  -> 合并画像匹配的专业候选
  -> 把 top documents 交给 Agent/GLM
  -> 生成带依据的报告
```

每条知识都是一行 JSON：

```json
{
  "id": "major_cs",
  "category": "major",
  "title": "计算机科学与技术",
  "content": "学习编程、算法、操作系统、数据库...",
  "tags": ["计算机", "软件", "高薪", "AI", "理工"],
  "source": "seed_major_profile"
}
```

## 这是不是 RAG

是 RAG 的轻量版本。

RAG 的核心不是必须使用向量数据库，而是：

1. 先从外部知识库检索相关资料。
2. 再把检索结果作为上下文交给大模型。
3. 让模型基于资料回答，而不是只靠模型记忆。

当前版本的 retriever 是 BM25/关键词检索；后续可以替换为 embedding + Chroma/FAISS。

## 为什么先不用 embedding

- 不需要额外 API 成本。
- 数据量只有几十到几百条时，关键词检索已经够用。
- 对中文专业名、城市名、规则标签这种短文本，标签和 BM25 很容易解释。
- 作业报告里可以清楚展示每条建议来自哪些资料。

## 后续升级

后续可以加一层向量检索：

```text
knowledge.jsonl
  -> embedding model
  -> Chroma/FAISS vector store
  -> semantic search
  -> rerank with profile rules
  -> GLM report generation
```

推荐保留 BM25 和标签检索，形成 hybrid retrieval：

```text
BM25 keyword score
+ vector similarity score
+ profile match score
+ source reliability score
= final retrieval score
```

这样既能搜到语义相关资料，也不会丢掉专业名、城市名、选科要求这种精确关键词。

