# 架构与扩展边界

## 制作流程

TXT → 只读源文本 → 人物／对白审校 → 章节制作方案 → 素材任务与回填 → 阅读编排 → 可编辑工程／独立阅读成品。

`storage.py` 管理原始字节、UTF-8副本、段落位置和任务。`review.py` 管理人物身份、别名、对白归属与人物素材。`production.py` 保存独立版本的全章风格、镜头预算与各镜头的具体瞬间、依据、视角、人物目的与可见行为。`reader.py` 与 `reader_presentation.py` 负责呈现配置，React阅读器负责连续阅读和个人进度。`speech.py` 管理音色、句子、缓存与已接受音频。`bundles.py` 提供可编辑工程迁移。既有 WebGAL 导出为可选后端。

制作方案通过原文完整段落结束位置挂载，程序核对引句确实存在；“这句是否支持这个心理判断”仍需人审。修改内容或全章风格会撤销对应镜头确认。应用方案仅更新该方案生成的插图，遇到手工插图位置冲突会明确报错。图片接受与镜头确认是两个状态。

## AI 接口

文本模型配置使用 `STORYGAL_LLM_API_KEY`、`STORYGAL_LLM_BASE_URL`、`STORYGAL_LLM_MODEL`。当前实现使用兼容 Chat Completions 的 JSON 响应；并非所有兼容服务都支持相同字段，服务返回须通过当前 schema 和原文锚点校验。按按钮才发送文本。人工修改有版本检查，模型延迟返回不能覆盖期间的新修改。

无密钥流程：下载 AI 方案任务（含 schema、正文段落与人物ID）→ 在自选工具处理 → 返回 `{source_sha256, plan}` → 导入并审校。生图任务由结构化方案编译，包含身份引用；用户自行携带对应参考图，图片完成后上传并回填。网页没有直接调用 Codex 会话生图的接口。扩展自动图片后端时必须显式声明参考图、透明背景、重试和费用能力，不能把“导入已有候选”伪装为自动生成。

## 内容包与示例

`samples/content-packs/catalog.json` 描述本地示例，包内格式与用户工程相同，通过 `/api/project-bundles` 导入。在 `samples/last-light/recipe.json` 中表达正文、人物、对白、镜头与文件；`tools/build_content_pack.py` 是通用构建器，调用公开接口，不识别小说名称。

赤壁工程包保留原编排，旧十二幅图尚未回填为新制作方案，查看与调整仍在“阅读器与场景”。现代样例完整展示新流程。赤壁历史专用编排保留兼容；其角色表、地图与旧快捷入口属于示例适配。新的样例不复制这些 Python 分支。历史地图的史料来源和约略坐标不能作为通用小说事实推断功能。

## 可编辑工程协议（v1兼容，v2见下方扩展）

ZIP 内包含 `manifest.json`（逐文件 SHA-256）、`project.json`（格式版本、原文元数据、固定类型制作记录）、两份源文本和实际PNG/WAV/可选SVG。不导出 SQLite、任务、密钥、模型缓存、操作日志、最终交付复核或浏览器个人记录。

导入保留作者的素材接受、人物审核和方案确认记录，含义是“原工程的制作状态”；新项目不继承最终发布确认。文件名、总展开体积（160MB）、重复条目、编号、类型、原文回拼、媒体格式和引用均校验。先在临时数据目录恢复，成功后以新项目ID原子提交，原项目不被覆盖。人物与素材ID在各项目内部保持稳定。

已接受的导入声音可在其他系统播放；修改读音、音色或表演指令会使对应记录不再匹配。新的合成仍依赖该系统实际支持的后端。包中未确认素材仍为未确认，不会因导入自动接受。

## 当前支持范围

单章／短篇，最多30,000字符；制作服务按macOS真实验证，Linux采用同一POSIX进程锁并配置自动检查，尚未在实体Linux机器验收。Windows建议WSL，原生Windows启动未实现。读者端使用浏览器。OpenAI语音适配准备沿用既有实现，本轮未实际调用云端。所有能力边界以实际验收记录为准。

## P11连续性与工程协议v2

`continuity.py` 保存场景母版、固定布局、物件定义和每个镜头的物件状态。固定物件不允许消失或修改位置；`offscreen`表示仍在场但未入画，`absent`表示此刻不在场。状态变更需要原因，原文物件依据逐字校验。镜头可声明复用、局部编辑或新视角，程序不据此承诺像素不变。

每个检查记录保存检查人类型（creator／assistant）、说明、时间和依赖哈希。哈希覆盖全章风格、场景定义及同场景截至当前镜头的全部制作数据，排除确认标记本身。普通保存无法伪造检查；修改上游依赖撤销相关记录。检查接口复用乐观版本控制，要求前序检查已完成。新生图任务v2携带母版、前序已检查图片引用及前后状态。

可编辑工程导出升级为v2，导入接受v1与v2；旧工程没有场景定义，默认未纳入连续性检查。导入外部AI方案清除检查记录；导入可编辑工程保留原作者检查并验证哈希，不继承最终发布复核。

可复建配方若含场景，需要`continuity-review.json`记录已检查配方、原文、人物立绘与场景图片的SHA-256、逐镜头检查说明及检查人类型。构建器在创建项目之前校验完整依赖集合，并使用同一批已校验字节构建；依赖缺失、多余或变化都会拒绝重放，要求重新检查。它不把新图自动标成已看过。

## Taleprism 0.1.0 prompt and release layers

`prompts.py` reads packaged `prompt_library.json`; the workbench and `tools/export_prompt_kit.py` consume the same rules. Exported Markdown contains copyable inputs and examples, and exported schemas come from runtime models. Image tasks retain format v2 and add template version/hash, ordered image responsibilities and a blocked flag when an upstream image is unchecked.

The public checkout includes canonical Last Light references, but excludes packed ZIPs and large historical image sets. `content-packs/catalog.json` gives versioned download URLs and hashes; missing files produce an explicit download/import flow. `tools/build_release.py` rebuilds the original recipe through the API with temporary storage, no system audio and no model calls, then verifies project migration and the independent reader. `tools/release_files.py` defines the public source inventory; local phase reports and runtime evidence remain local.

## 可靠性修复：恢复、检查与发布的边界

可编辑工程恢复验证结构、原文、锚点、引用存在与所属、文件类型和完整性；人物暂未确认、引用素材已拒绝属于可恢复的制作状态。导入保留这些记录并返回修复提示，不能把不完整的制作工作自动变为发布许可。图片不存在或属于错误人物、原文锚点不合法、文件损坏仍拒绝导入。持久化语音配置使用独立模型，保存云端模型标识，不把带有请求版本号的表单模型当作文件格式。

连续性检查明确区分通过、不通过、撤销和过期。检查保留署名、观察说明及依据；依据包括原文校验值、实际使用的情境图和人物参考。更换参与人物的启用参考在同一事务中撤销依赖它的检查，换回旧参考也不能自动恢复原来的通过状态。复审不通过或撤销时，后续依赖镜头必须重新按序核对。旧检查缺少完整依据时可读取其原记录，但要求重新复核，不自动补造历史检查依据。

配方重建在创建项目之前验证完整输入清单：原文、所有人物参考及情境图。清单和文件不一致或旧清单缺少这些依据时停止重放；构建器不能自行生成新校验值并冒充既有审查。末班灯既有记录的依赖补录保留原署名、说明与最终美术待审状态。

对白归属实际改变时，在同一事务中清除相应音频的接受映射并更新配音版本，原音频文件保留。无关对白或没有改变归属的操作不撤销其接受记录；迁移后的未改音频仍可跨系统播放。

独立阅读器导出和交付检查验证已应用的方案插图及其必要前序。未应用的无关草稿不阻断成品；已经应用的镜头检查被撤销或失效后，不能通过旧的阅读编排绕过复核。制作方案版本加入导出期间的一致性校验与交付复核，打包中途发生修改会清理未完成产物；已完成的旧成品保持原快照。

合并人物时在同一事务中使相关检查失效。恢复旧编排与历史检查时只接受存在且无循环的合并链，不改写原人物引用或自动确认；不存在的目标、循环合并、无关人物的图片仍拒绝导入。最终复核写入事务与导出共用版本校验，防止前置检查后发生的撤销被遗漏。
