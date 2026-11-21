# Taleprism 0.9.2 · 让画服务于这一段 / Should this illustration move?

## 下载：只选你需要的包

**用自己的小说开始 → [下载 AI 创作入门包（Prompt Starter）](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.2/taleprism-v0.9.2-prompt-starter.zip)**。解压到本地，把一章原文和模板交给自己的 Agent；不用先安装制作台。第一句话和产物去向见 [Agent 手顺](../prompts/START-HERE.md#中文手顺)。

| 其他用途 | 看文件名 |
| --- | --- |
| 只读成品 | `-reader.zip`；完整解压后打开 `index.html`。《赤壁》也可[在线读](https://ethereal-space-one.github.io/taleprism/index.html)。 |
| 在制作台复现或改示例 | `-project.zip`；只有《赤壁》《末班灯》，从制作台导入，不是插件或读本。 |
| 安装本地制作台 | `-source.zip`；解压后按[安装文档](快速上手.md)操作。GitHub 自动附带的 Source code 快照也不是创作包。 |
| 校验下载 | `SHA256SUMS`、`release-manifest.json`；日常使用不用下载。 |

## Which download do I need?

**Bring your own novel → [Download the AI Author Starter](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.2/taleprism-v0.9.2-prompt-starter.zip)**. Extract it and give your agent the templates and one chapter. No workbench installation is needed for the first pass. See the [agent walkthrough](../prompts/START-HERE.md#english-walkthrough). Pick a `-reader.zip` only to read, a `-project.zip` only to edit an example, or `-source.zip` to install the local workbench. The checksum and manifest are optional verification files.

## 本版改了什么 / What changed

《留白处》的桌脚少了一角，两册旧历书把它托平了。这幅画该给读者时间自己看，而不是掀动几张书页替读者指出答案。《赤壁》写「忽聽風聲響，旗旛轉動」，帐里的布尾确实值得一动，但现有的雨线、岸浪都做不好布料受风。这两张成图都不动，理由却不一样。

**给作者。** 在「独立阅读器 → 逐幅动静审图」打开实际入书的插图，对照它出现时已经读到的原句。写下所见、保护区和理由，选择留静、可支持的动效候选，或值得做但暂不支持。正式交付签核需审完每幅；仍可随时导出草稿试读。换原文、图或落点时旧判断不能冒充新结论。审图不调用模型，也不自动加动画。工作表单独保存，不混进读本或工程备份。

| 读本 / Reader | 入书插图 / Plates | 留静 / Still | 延期 / Deferred | 已有动效 / Existing motion |
| --- | ---: | ---: | ---: | ---: |
| 赤壁 / Chibi | 12 | 9 | 2 | 1 |
| 末班灯 / Last Light | 3 | 2 | 0 | 1 |
| 留门 / The Door Left Open | 1 | 0 | 0 | 1 |
| 留白处 / The Margin | 1 | 1 | 0 | 0 |
| **合计 / Total** | **17** | **12** | **2** | **3** |

**给读者。** 四份离线读本和两份可编辑示例的 ZIP 内容与 0.9.1 逐字节相同，已有下载不用换。三处动效依旧是《赤壁》首幅岸浪、《末班灯》首幅站台雨和《留门》的湿路雨。开篇岸浪会盖住一小处前景松枝；检测到播放，不等于遮挡已修。本次没有新增动效、重画插图或修改图解操作。

**For authors.** Open each placed plate in the workbench and compare the actual image with a quotation the reader has reached. Record what the reader should notice, what should not move, and why you would keep the image still, propose a supported local effect, or leave a worthwhile idea for later. All three are valid editorial decisions. A new or changed plate is not signed off by default. The worksheet does not operate the renderer. Save it separately; restoring an exact editable copy and adopting its worksheet are two distinct steps.

**For readers.** The four reader ZIPs and two editable examples are byte-for-byte the 0.9.1 editions, under 0.9.2 download names. Existing copies need no update. This release changes the workbench, source and prompt starter. Normal playback can be tested separately from reduced-motion behavior and visual quality: the first Chibi wave still crosses part of a foreground pine branch. No new animation, art, graph controls or playback behavior is included.

[开始逐幅审图 / Workflow](PLATE-SCREENING.md) · [逐书判读 / Worked examples](../examples/plate-screening/README.md) · [验收与边界 / Acceptance](VALIDATION-v0.9.2.md) · [下载 / Downloads](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.9.2)
