# WebGAL 引擎

导出用的 WebGAL 网页版引擎不进 git，运行下面的脚本下载并校验：

```bash
tools/fetch_engine.sh
```

脚本固定版本 4.6.5（与 `tools/webgal-verify` 里的 `webgal-parser` 一致），从 OpenWebGAL/WebGAL 的 GitHub Release 下载，校验 SHA-256 后解压到 `engine/webgal-4.6.5/`。WebGAL 以 MPL-2.0 发布，导出工程会附带它的许可证。
