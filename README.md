# Taleprism

**保留小说原文，让人物、场景与声音共同构成连续的阅读体验。**

从人物立场与心理表演，到场景母版、道具状态、逐图检查和定点修复：Taleprism 把制作经验整理成可复制的提示词工作流，并提供本地制作台。

**v0.3.0 公开试用版** · [English](README.en.md) · [直接阅读《赤壁》](https://ethereal-space-one.github.io/taleprism/) · [下载与版本说明](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.3.0)

![赤壁：七星坛祭风，三江口纵火](examples/chibi/cover.png)

**赤壁展示阅读体验，《末班灯》讲解制作方法。** 在线主示例包含 12 幅情境插图、8 位主要角色、9 张立绘和三个阶段的战区地图；[短篇教程与素材](examples/last-light/README.md)完整保留在仓库。

## 选择你的开始方式

| 我想做什么 | 从这里开始 |
| --- | --- |
| 先看成品 | [在线阅读《赤壁》](https://ethereal-space-one.github.io/taleprism/)，无需安装 |
| 在自己的 AI 工具里尝试 | [八个提示词模板](prompts/README.md) → [完整三镜头教程](examples/last-light/README.md)，无需安装制作台 |
| 制作、审校并导出一章 | 按下方步骤安装本地制作台，再导入示例工程或自己的 TXT |

模板和示例可免费获取；你选择的 AI 服务可能需要账户并产生费用。浏览成品、手工编排与已有素材导入不需要模型密钥。图片由外部工具生成后回填，网页不会直接调用 Codex 会话内生图。

## 本地制作台

需要 Python 3.11+（由 uv 管理亦可）、[uv](https://docs.astral.sh/uv/getting-started/installation/)、Node.js 22.12+ 与 npm。当前界面为中文；macOS 是主要人工验证环境，平台范围见[验证记录](docs/VALIDATION-v0.3.0.md)。

```sh
git clone https://github.com/Ethereal-Space-one/taleprism.git
cd taleprism
./start.sh
```

首次安装联网下载依赖。打开 <http://127.0.0.1:8000>。以后用 `./run.sh`；macOS 也可双击“打开Taleprism.command”。服务只监听本机。电脑重启后需要重新启动。

在左侧“示例与工程”选择《赤壁》或《末班灯》，从下载入口取得对应的 `project.zip`，再点“导入可编辑工程”。赤壁用于完整章节与群像制作，末班灯用于三镜头入门。也可点“从《末班灯》原文练习”只导入正文，从头制作。示例工程单独下载。

两种工程均包含原文、素材、制作方案及助手检查依据；公开样例不含 macOS 系统演示音频。每次导入新建项目，保留原工程。未完成审校的工程可恢复后继续修复，旧检查缺少依据时需重新复核。详细步骤见[快速上手](docs/快速上手.md)。

## 这套流程解决什么

1. **忠于原文**：原始文件与工作文本只读保留，镜头依据落到具体段落。
2. **人物有自己的立场**：分别写目标、所知、公开姿态、顾虑和可见动作，避免两个人共享一种笼统情绪。
3. **画面有叙事职责**：用有限图片建立空间、展现关系和心理变化，不机械地每隔几段换图。
4. **同地点能连续**：母版固定布局，状态表说明物件去向；画外不等于消失。
5. **错误可追查**：生成后检查真实图片、定点修复，上游变化会使相关后续检查失效。
6. **成品可以带走**：可编辑工程用于迁移，独立阅读器用于分享，无需制作台后端。

[《末班灯》教程](examples/last-light/README.md)保留了长凳变长、车篮遗漏的实际返工经验，以及旧流程与连续性修订的对比。模板与制作台读取同一份规则；模板版本和任务格式有独立版本记录。

## 下载哪一个包

附件在 [v0.3.0 Release](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.3.0)，统一对照 `SHA256SUMS` 与 `release-manifest.json`。旧版附件仍保留在原 Release。

| 文件结尾 | 用途 |
| --- | --- |
| `prompt-starter.zip` | 模板、原创原文、参考图、完整教程；不安装程序也能用 |
| `last-light-project.zip` | 可继续编辑的《末班灯》工程，导入制作台 |
| `chibi-project.zip` | 赤壁完整可编辑工程，含十二镜头制作方案与检查依据 |
| `chibi-reader.zip` | 赤壁在线主体验的完整独立阅读包 |
| `last-light-reader.zip` | 已完成的独立阅读成品；解压后用 HTTP 服务打开 |
| `source.zip` 或 GitHub 的 Source code ZIP | 制作台源码与教程参考图；完整工程另行下载 |

独立阅读包解压后，在该目录运行：

```sh
python3 verify_package.py
python3 -m http.server 8080 --bind 127.0.0.1
```

然后访问 <http://127.0.0.1:8080>；不要直接双击 HTML。

## 可选服务与试用边界

- 文本 AI：在本机 `.env` 配置兼容接口；只有主动执行 AI 操作才发送文本。无密钥也可导出任务，在自己的工具中处理后导入。
- 图片：使用支持参考图/编辑的外部工具，完成后上传审校。本案例用 Codex 会话内生图；其他模型与任意反打、绕拍尚未验证。
- 声音：macOS 中文系统音色与 ffmpeg 可本地合成，已有音频可随工程迁移播放。OpenAI 配音适配器已准备，真实云端调用与音色效果尚未验证。
- 内容范围：单章或短篇 TXT，最多 30,000 字；不提供整本小说一键制作或自动艺术验收。
- 兼容：内部 `storygal` 模块、`STORYGAL_*` 配置、旧工程格式和阅读进度键保留，见[兼容说明](docs/COMPATIBILITY.md)。Windows 原生启动未支持。
- 试用状态：助手制作检查不等于创作者最终美术复核；外部用户独立上手尚待验证。

可选 WebGAL 兼容导出使用 `./start.sh --with-webgal`。[赤壁](examples/chibi/README.md)是在线主体验，专用历史地图用于理解驻扎与进军关系；它不是通用地图生成服务。

## 参与与来源

[贡献指南](CONTRIBUTING.md) · [架构](docs/ARCHITECTURE.md) · [人物视觉导演标准](docs/人物视觉导演标准.md) · [更新记录](CHANGELOG.md) · [问题反馈](https://github.com/Ethereal-Space-one/taleprism/issues/new/choose)

项目代码和提示词采用 [MIT](LICENSE)。小说、图片、声音和依赖分别保留[来源与许可](THIRD_PARTY_NOTICES.md)；AI 素材不承诺独占性。Taleprism 的早期本地名称为“原页 / Storygal”，原贡献声明继续保留。
