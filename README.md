# Taleprism

**保留小说的每一个字，让读者在读到时看清局势、听见街声。** Taleprism 是一座本地制作台，也是一种不必安装的读本。图、声、动效都有原文里的落点；段落不需要它们时，页面就只有文字。

**[从《赤壁》开始读](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.0/taleprism-v0.9.0-chibi-reader.zip) · [再听《留门》里的雨](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.0/taleprism-v0.9.0-the-door-left-open-reader.zip)** · [v0.9.0 公开预览与全部下载](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.9.0) · [English](README.en.md)

## 古典主展：《赤壁》把战局留在读者读到的那一刻

![《赤壁》封面：七星坛祭风与三江口火攻](examples/chibi/cover.png)

《三国演义》第四十九、五十回里，人会换营，船会移位。地图若一开始就画出撤军路线，等于把结局印在了第一页。这里的三阶段地图、阵营关系和事件因果随原文进度展开；向前读才看见新局势，回读时收起后文的结果。可以看已经读到的图，不必先打开整章图集。

十二幅情境插图安放在具体段落，八位主要人物有各自的立场。人物在上一幅图看见了什么、上过哪条船，不能因为下一幅换了机位就当作没发生。这个版本不加配音或背景声，靠原句、人物与图版把战局说清。想看编排怎么做的，可以[导入《赤壁》可编辑工程](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.0/taleprism-v0.9.0-chibi-project.zip)，对照[镜头与连续性记录](examples/chibi/README.md)。

## 现代主展：《留门》只让街上的雨动起来

修鞋铺的卷门放到一半，门槛上留着一双小黄靴。第一段没有声音；读到第二段，才听见雨落在铁篷上，一辆车从巷口驶过。十二秒里，第六秒车最近。图上的雨线只落在右侧湿路，靴子和干门槛始终不动。结尾雨停，声音也没有理由再来。

[《留门》阅读包](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.0/taleprism-v0.9.0-the-door-left-open-reader.zip)最适合试 0.9 的「随文演绎」。另一个小实验[《留白处》](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.0/taleprism-v0.9.0-the-margin-reader.zip)反而让静物画始终静止：读到后段，折页才带回前文的一句话；末段只有几笔铅笔声。两本都只发读本，不附可编辑项目。

## 怎么读？封面不响，正文不替你翻页

1. 下载 **Reader ZIP → 完整解压 → 双击文件夹内的 `index.html`**。保留旁边的素材文件夹，不要在 ZIP 预览里打开。不需要终端、网络、制作台或模型密钥。
2. 选「开始阅读」，已经采用的声景读到时响一次，图在作者选定的位置出现；只有另行复核的局部动效才动。若浏览器拦住第一次声音，点阅读器内的提示即可，不必放宽系统权限。
3. 选「安静阅读」就改为手动体验。正文可暂停自动演绎；「静音」关整部作品的声音，但保留画与折页。系统开启「减少动态效果」时，图保持静止。段落朗读仍需点听，人物对白另有设置。

**线上和下载不是同一版。** [在线《赤壁》](https://ethereal-space-one.github.io/taleprism/)是此前部署的 **0.3.2**；**0.3.3** 是此前的 GitHub 公开预览，不是当前 Pages 版本。本次 **0.9.0** 读本从上方 Release 下载，不会替换网页或你手上的旧 ZIP。

## 做自己的读本：先选原句，再决定做不做

从「用自己的图文开始」导入 TXT。给一段原文放上一张自己有权使用的画，检查底图、定好位置，这就已经能导出。需要听见什么时，再导入一段获许可的朗读，或编排短声景；听完、确认采用，才进入读本。要让画动，就在实际图上圈出雨区或岸线，预览、复核，而非让整幅画都动。

制作收尾的 **One More Thing** 默认收起：可从声音、影像或呈现方式中选一项，看看是否有值得尝试的提案；「都不加」也是完成。本机规则不是模型；主动请求外部模型时会先确认正文与接口。只有作者采用的安排才交给读者，阅读时不会调用 AI。**分享用 Reader，续作用工程备份**；后者可能包含未用素材、注释和审校历史。

第一次制作可跟[《末班灯》三镜头教程](examples/last-light/README.md)。运行本地工作台需 Python 3.11+、[uv](https://docs.astral.sh/uv/getting-started/installation/)、Node.js 22.12+ 和 npm；在源码中含 `start.sh` 的目录执行 `./start.sh`，依提示打开本机地址。首次安装需要联网，之后在同目录用 `./run.sh`。工作台界面为中文，无原生 Windows 启动器。

[快速上手](docs/快速上手.md) · [八个制作提示词](prompts/README.md) · [公开复现实验](examples/reading-lab/README.md) · [逐版迭代记录](docs/ITERATION-HISTORY.md) · [本版实测与边界](docs/VALIDATION-v0.9.0.md) · [贡献指南](CONTRIBUTING.md)

代码及提示词采用 [MIT](LICENSE)。作品、媒体、依赖的[来源与许可](THIRD_PARTY_NOTICES.md)另列；请同时保留读本附带的说明。
