# 截图证据踩坑记录（#14–#18）

> 状态：v0.1 已收敛（response #18 验收可用）  
> 代码：`apps/api/app/providers/deepseek_web.py` → `_capture_answer_evidence`  
> 相关：`docs/17-playwright-fullpage-screenshot.md`

---

## 1. 截图在哪里抓？

| 项 | 答案 |
|----|------|
| 运行位置 | **VPS** `geo-crawler` 容器内 |
| 引擎 | Playwright **无头 Chromium** |
| 本机 Mac Chrome | **不参与**抓取截图（仅曾用于导出 `storage_state` 登录态） |
| 产物路径 | 容器 `/data/screenshots/deepseek_*.png`（volume `crawl_data`） |
| QA 访问 | `http://VPS:8200/qa/media/screenshots/{filename}` |

**结论：** 证据截图永远是 crawler 进程写盘，不是你本机浏览器。

---

## 2. 用户要什么 vs 错误证据长什么样

**要（参考期望）：**
- 完整回答正文（表格、列表、全文）
- 可选：问题气泡
- **不要**侧栏历史、底部输入框、半截视口

**错（#14–#17 一类）：**
- 左侧「开启新对话」+ 历史列表
- 中间输入框
- 只截到视口或内部 scroller 可见区
- 或路径写了但 `/qa/media` 404（另 bug，已修）

---

## 3. 走过的错误路线（勿再犯）

| 尝试 | 为何失败 |
|------|----------|
| `page.screenshot(full_page=False)` | 仅视口，回答被裁切 |
| live 页 `full_page=True` | DeepSeek **内部滚动容器**，document.scrollHeight ≠ 回答全文；侧栏仍在 |
| 只 `element.screenshot` 回答节点 | 父级 overflow 裁剪 / 布局仍夹杂 UI chrome |
| 展开 scroller 后再 live full_page | 仍常混入侧栏/composer（#17） |
| 复杂 `page.evaluate` 抽 HTML | 曾触发 `SyntaxError: Invalid or unexpected token`（job #23）；大段内联 JS + 参数序列化不稳 |
| **改了 worktree 不 rebuild crawler** | post-receive 早期只 build **api**；crawler 镜像仍是旧截图逻辑 → #17 仍是坏图 |

---

## 4. 当前正确实现（#18 / commit `a2e70bb`）

### 主路径：clean-render + full_page

```
DeepSeek 答完
  → Playwright locator 选最长/最匹配的 .ds-markdown
  → inner_html() 拿完整回答 HTML（表格/列表保留）
  → context.new_page()
  → set_content(深色卡片 HTML：问题气泡 + answer 正文 + 基础 markdown 样式)
  → screenshot(path=..., full_page=True)
  → close 证据页
```

要点：
1. **不在 live DeepSeek DOM 上追求「完美整页」**——先**抽内容**再**独立渲染**。
2. 问题文案优先用本次 `prompt` 入参，不依赖 DOM 猜问题。
3. 抽 HTML 用 **locator API**，避免脆弱的大段 `page.evaluate`。
4. `full_page=True` 用在**我们自己的短文档页**上，文档高度 = 回答高度，没有侧栏。

### 回退路径

clean-render 失败时才：
- CSS 隐藏 sidebar / composer  
- 撑开内部 overflow scroller  
- live `full_page=True`

日志关键字：
- 成功主路径：`evidence clean-render full_page saved ... html_len=...`
- 回退：`evidence live full_page fallback saved`

---

## 5. 部署纪律（必守）

1. 本地改 `deepseek_web.py` → `git push vps main`
2. 确认 **worktree 与镜像一致**：  
   `docker exec geo-crawler grep -n 'Playwright locator API' /app/apps/api/app/providers/deepseek_web.py`
3. crawler 有改动必须 **rebuild 镜像**（代码 COPY 进 image，不是 bind-mount）  
   现 hook：容器名 `geo-crawler` 存在时会 `compose --profile crawl up -d --build crawler`
4. `deepseek_storage.json` 在 volume `/data`；rebuild **不删** volume，但新 volume 要 seed 一次
5. **旧 response 的截图不会自动重生成**——验收必须 **新开 crawl job** 看最新 id

验证命令示例：

```bash
curl -s -X POST http://127.0.0.1:8200/v1/crawl-jobs \
  -H 'Content-Type: application/json' \
  -d '{"prompt_id":1,"platform":"deepseek","samples":1}'
docker logs geo-crawler --since 5m | grep -E 'clean-render|fallback|success|failed'
# 打开 /qa/responses/{最新id} 看截图
```

---

## 6. 与「Playwright 全页截图文档」的关系

通用文档（`docs/17-...`）说：`full_page=True` = 按 **document 滚动高度** 拼长图。

对本项目：
- 该参数**仍然必要**（独立卡片页要一次截全）
- 但**不能**指望它单独解决 SPA 聊天页的侧栏 + 内部 scroller
- 正确组合是：**内容抽取 + 空白页渲染 + full_page**

---

## 7. 证据策略（产品约定）

- **只保留截图路径**，不落库 DeepSeek 对话 URL（多会话上下文串扰）
- L0：`screenshot_path` + `full_text` + citations…
- QA：列表可点进详情；详情可展开全文 + 预览/原图

---

## 8. 验收样本

| id | 文件 | 结果 |
|----|------|------|
| ≤17 | live/旧逻辑 | 侧栏/composer/半截，不合格 |
| 18 | `deepseek_1785479863.png` | clean-render，1100×1340，合格 |

日志：`html_len=10557 text_len=1378` → 说明抽到了完整 HTML，不是空壳。

