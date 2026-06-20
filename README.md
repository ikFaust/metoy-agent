# Metoy 科学小导师

面向学生的科学学习 Agent 原型。它结合 GLM API、本地 RAG 知识库和教具目录工具，让学生可以通过聊天学习科学知识，并在需要时获得基于真实教具说明书的实验指导。

## 功能

- 学生聊天界面：像聊天助手一样直接提问。
- 开发者控制台：查看 Agent 轨迹、RAG 依据、质量校验。
- 本地知识库：教材、论文、教具说明书索引。
- 教具目录工具：回答“有哪些教具”时只使用本地说明书，不让模型编造。
- 上下文记忆：支持“下一步”“怎么验证呢”等追问。
- GLM 智能生成：通过智谱 OpenAI-compatible API 调用模型。
- 商店入口：在应用里查看教具商店展示页。

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

在 `.env` 中配置：

```bash
ZHIPU_API_KEY=你的智谱APIKey
ZHIPU_MODEL=glm-4.5-air
```

如果没有配置 `ZHIPU_API_KEY`，应用仍可用本地规则兜底运行，但智能生成效果会下降。

## Agent 架构

```text
User Message
  -> Profile / State
  -> Memory Resolver
  -> Router
  -> Tool Registry
  -> Local RAG / Teaching Aid Catalog
  -> Reason / Experiment Design
  -> Safety Check
  -> GLM or Rule Generator
  -> Quality Verifier
  -> Student UI / Developer Console
```

## 部署说明

线上部署不要上传 `.env`。请在部署平台的环境变量里配置 `ZHIPU_API_KEY`。

项目上线只需要这些核心文件：

- `app.py`
- `edutoy/`
- `futuremajor/`
- `data/`
- `docs/`
- `requirements.txt`
- `deepseek_html_20260620_f1cabf.html`
- `.streamlit/config.toml`

原始资料文件夹 `新的设计/` 和大作业 PDF 只用于本地构建知识库，不需要上传到线上。
