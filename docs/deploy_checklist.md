# GitHub + Render 部署前检查清单

## 本地已经完成

- [x] 应用可在 `http://localhost:8501` 本地运行。
- [x] `requirements.txt` 已存在。
- [x] `render.yaml` 已存在。
- [x] `Dockerfile` 已存在。
- [x] `.streamlit/config.toml` 已存在。
- [x] `.env` 已被 `.gitignore` 忽略。
- [x] `新的设计/` 原始大资料已被 `.gitignore` 忽略。
- [x] `data/edutoy/documents.jsonl` 会被上传，线上 RAG 有资料。

## 你需要准备

- [ ] 一个 GitHub 账号。
- [ ] 一个 Render 账号。
- [ ] 一个新的 GLM API Key。

建议重新生成 GLM Key，因为旧 Key 曾经出现在聊天记录里。

## 上传 GitHub 时应该包含

```text
app.py
requirements.txt
README.md
DEPLOY.md
Dockerfile
render.yaml
.dockerignore
.gitignore
.env.example
.streamlit/config.toml
data/
docs/
edutoy/
futuremajor/
scripts/
deepseek_html_20260620_f1cabf.html
```

## 上传 GitHub 时不应该包含

```text
.env
.venv/
新的设计/
从0构建大模型_大作业.pdf
.DS_Store
```

## Render 环境变量

```bash
ZHIPU_API_KEY=你的新GLM_API_Key
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_MODEL=glm-4.5-air
ZHIPU_THINKING=disabled
ZHIPU_MAX_TOKENS=900
ZHIPU_TEMPERATURE=0.55
ZHIPU_TIMEOUT=18
```

## 部署完成后测试

- [ ] 打开 Render 给出的公网网址。
- [ ] 问：`彩虹是怎么形成的？`
- [ ] 问：`你们有哪些教具？`
- [ ] 问：`我想用平面镜成像演示仪学习平面镜成像，请带我一步步做实验。`
- [ ] 追问：`下一步呢？`
- [ ] 打开开发者控制台，确认 RAG 依据和 Agent 轨迹能显示。
- [ ] 点击左侧购物车图标，确认商店页面能打开。
