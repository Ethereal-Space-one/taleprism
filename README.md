# ![Taleprism](docs/media/taleprism-chibi-title.webp)

**以原文为底，让插图、声景与图解随叙事展开。**

[**在线读《赤壁》 →**](https://ethereal-space-one.github.io/taleprism/)　·　[**用自己的小说开始 →**](#用自己的小说先做一页)

![《赤壁》读本原封面：暮色江岸，人物望向江面](docs/media/chibi-cover.webp)

*《赤壁》 · 实际读本封面*

## 一处画面，一处声音

<table>
<tr>
<td width="50%" valign="top">
<img src="docs/media/chibi-wind-in-tent.webp" alt="《赤壁》风先入帐：帐帘与布尾掀起，灯火照亮案前" width="100%"><br>
<strong>《赤壁》 · 风先入帐</strong><br>
读到旗旛转动，才听见这一阵风。
</td>
<td width="50%" valign="top">
<img src="docs/media/the-door-left-open.webp" alt="《留门》修鞋铺外，黄色小靴留在干门槛上" width="100%"><br>
<strong>《留门》 · 街雨落在门外</strong><br>
黄靴不动，雨和车声只经过这一段。
</td>
</tr>
</table>

《赤壁》的战区地图、阵营关系和事件脉络随正文展开，回读时也收起后文的结果。想直接体验声景，打开《赤壁》搜 `旗旛轉動`，点该段末的「听此处声景 · 风声」。这是一处合成风声，不是整章背景乐；正常向前阅读才会触发自动演绎。「风先入帐」是随后出场的静图，不把声音冒充动画。

《留门》把雨线留在图的右侧湿路，干门槛和靴子不动。你也可以用「安静阅读」手动体验，或随时暂停、静音；开启系统「减少动态效果」时，插图保持静止。

## 用自己的小说，先做一页

1. **只下一包。** [下载 AI 创作入门包](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.3/taleprism-agent-starter.zip)，解压后在含 `prompts/` 的目录放入一章原文，例如 `chapter.txt`。用 Codex 或 Claude Code 打开这个目录；只能上传附件时，交给它原文和下面两份模板即可。
2. **先让 Agent 给一页镜头方案，不急着生图。** 把这句话交给它：

   > 用 Taleprism 处理这一章。先读 `prompts/01-source.md`、`prompts/03-shot-plan.md` 和 `chapter.txt`，或对应附件。原文一个字不改，只选 1–3 处适合插图的段落。每处列出段落、逐字引文、画面要让读者看懂什么、不能提前揭示什么；推断另列。输出 Markdown，等我确认再生图。

3. **确认后再成书。** 用你选的图片工具出图。要分享成品时才打开制作台，把原 TXT 和成图放到对应段落，试读后导出独立读本。

入门包不是插件，也不需要 Taleprism 密钥。图片、配音或模型服务由你自己选择。[更完整的 Agent 手顺](prompts/START-HERE.md#中文手顺)

## 拆开一部成品，或者做自己的

**《赤壁》**适合看群像、战局和章节编排；**《末班灯》**适合跟着三镜头练习人物、机位和道具连续性。两部作品各一个 ZIP：解压后打开 `Reader/index.html` 试读，或把同包的 `Project.zip` 导入制作台继续做。《留门》《留白处》是只读示例。

想装本地制作台，下载源码包并在解压目录运行 `./start.sh`（需 Python 3.11+、uv、Node.js 22.12+ 和 npm，首次安装需联网）。之后运行 `./run.sh`，macOS 也可以双击「打开Taleprism.command」。

**[所有作品与下载](docs/DOWNLOADS.md)**　·　[制作台安装与详细手顺](docs/快速上手.md)

## 不必让每幅画都动

每张成图都对照原句审查，留静也是决定。收尾时可让 AI 在声音、影像或呈现方式上再提一个点子；「都不加」也算完成。只有作者采用的安排会进入读本，读者阅读时不会调用 AI。分享用读本，继续制作请另存可编辑工程。

[v0.9.3 发布说明](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.9.3)　·　[English](README.en.md)
