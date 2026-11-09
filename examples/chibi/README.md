# 赤壁 · 在线主体验

[直接阅读](https://ethereal-space-one.github.io/taleprism/) · [下载独立阅读包](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.1.0/taleprism-v0.1.0-chibi-reader.zip) · [短篇制作教程《末班灯》](../last-light/README.md)

用《三国演义》第四十九、五十回展示连续读一章的体验：12 幅情境插图、8 位主要角色、9 张立绘、55 段画面编排，以及夹江对峙、火攻推进、战后撤军三个地图阶段。默认采用插图阅读，设置中可切换图文分栏；地图从阅读器内打开。

赤壁负责展示人物、群像和历史空间；《末班灯》保留为易于复现的三镜头短篇教程，包含原文、参考图、完整工作表、提示词和连续性修复记录。

## 来源和制作状态

- 正文保持[原文件](../../samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt)，版本与整理方式见[来源记录](../../samples/sanguo-chibi/PROVENANCE.md)。
- 封面为原有 `cover-v1.png` 的原样副本，SHA-256：`3198aba1b52fc9a7b643d83bbc401d0af6c8c42956a9cf31fb3eae8ca514d45c`。图片来源见[第三方与素材说明](../../THIRD_PARTY_NOTICES.md)；阅读包内也保留制作来源文件。
- [地图](../../samples/reader/chibi-map.json)用于辅助理解阵营、驻扎与行进关系，是约略历史图解，不是精确坐标复原或通用地图生成服务。
- 本次对“帐中问疾”“华容相逢”两幅修订图进行了实际图片检查，记录在 [demo-review.json](demo-review.json)。仅在临时公开示例副本中接受这两幅图；原始工程与原始待审记录保持不变。助手制作检查不代填创作者最终美术复核。
- 公开阅读包不包含本机系统演示语音；其余声音接入能力见主项目说明。

## 复现与完整性

`examples/site.json` 指定在线主示例，内容目录固定下载文件及校验值。页面部署先验证整个 ZIP 和每个内部文件，再发布。

完整历史制作包保存在维护者本机；Git 保留正文、导演/地图资料和检查记录，大型阅读媒体随 Release 下载。拥有匹配原始制作包时，可构建临时副本：

```sh
uv run --project backend python tools/build_chibi_demo.py --source /path/to/chibi.storygal.zip
```

脚本检查原包和已检查图片的哈希、正文完整性、图片/人物/地图数量，并排除本机演示音频。内容发生变化时应重新检查并记录；不能直接改哈希来绕过检查。公开的 v0.1.0 原有附件保持不变，赤壁阅读包作为单独新增附件发布。
