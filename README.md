# Frame on Mac mini Starter

这是一个面向 `Brilliant Labs Frame + macOS` 的最小开发起步工程，目标是让你先跑通：

- Mac mini 通过蓝牙连接 Frame
- 从终端把文本推送到眼镜显示
- 用标准输入把日志、AI 输出、字幕原型推到眼镜
- 直接运行命令，并把关键结果同步到眼镜做 `Dev HUD`
- 通过麦克风抓音并把字幕同步到眼镜做 `Meeting HUD`
- 用官方 `text_sprite_block` 通路显示中文和其他 Unicode 字幕
- 做实时会议翻译 HUD，支持英文直译和任意目标语言翻译
- 做可选的说话人标签 HUD，用 `A:`、`B:` 区分不同发言人
- 做 `tap-to-capture Vision HUD`，轻点眼镜一下就拍照并分析

如果你是第一次开发 Frame，建议先把这套 starter 跑通，再继续做语音字幕、视觉问答、开发者 HUD 等更有趣的功能。

## 1. 环境准备

- macOS 上的 `Python 3.9+`
- 一副已开机、可被蓝牙发现的 Frame
- 终端应用具备蓝牙权限

推荐先安装 Xcode Command Line Tools：

```bash
xcode-select --install
```

如果你准备做 `Meeting HUD`，建议额外安装：

```bash
brew install portaudio ffmpeg tesseract
```

## 2. 安装依赖

基础依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

会议字幕依赖：

```bash
pip install -r requirements-meeting.txt
```

会议翻译依赖：

```bash
pip install -r requirements-translation.txt
```

说话人标签依赖：

```bash
pip install -r requirements-speaker.txt
```

视觉 HUD 依赖：

```bash
pip install -r requirements-vision.txt
```

说明：

- 官方当前主推的 Python 路线是 `frame-ble` + `frame-msg`
- 我本地验证时，`frame-msg` 还需要补齐 `numpy`、`Pillow`、`lz4` 才能完整导入，所以这里直接写进依赖
- `Meeting HUD` 使用 `faster-whisper` 做本地转写，首次运行会下载模型
- `OpenAI` 翻译模式需要设置 `OPENAI_API_KEY`
- `pyannote` 说话人区分需要设置 `HUGGINGFACE_TOKEN`，并在 Hugging Face 上接受相应模型条款

## 2.1 先扫描附近的 Frame

如果你不确定设备名，先扫一遍附近可连的 Frame：

```bash
source .venv/bin/activate
python examples/scan_frame.py
```

如果你想按名字过滤：

```bash
python examples/scan_frame.py --name-contains "Frame"
```

如果你刚在 macOS 里把设备忘记了，建议顺序是：

1. 在 `系统设置 -> 蓝牙` 里对 `Frame` 选择 `忽略此设备`
2. 关闭再打开 `Frame`
3. 运行 `python examples/scan_frame.py` 确认它重新广播了
4. 再运行 `python examples/send_text.py --name "Frame 4F" --text "Hello"`

## 2.2 统一入口命令

如果你不想记很多脚本文件名，可以直接用统一入口：

```bash
source .venv/bin/activate
python frame_lab.py scan
python frame_lab.py say -- --name "Frame 4F" --text "Hello"
python frame_lab.py meeting -- --demo --render-mode unicode
python frame_lab.py vision -- --source demo --analyzer mock --dry-run
python frame_lab.py tap-vision -- --demo
```

说明：

- 第一个参数是子命令，例如 `scan`、`say`、`meeting`
- 子命令后面的参数会原样传给对应脚本
- 如果你想更清楚地区分 launcher 参数和脚本参数，建议加一个 `--`

## 3. 第一次连接测试

把一句话直接显示到眼镜上：

```bash
source .venv/bin/activate
python examples/send_text.py --text "Hello from Mac mini"
```

如果你手边暂时没连眼镜，也可以先本地验证：

```bash
python examples/send_text.py --text "Hello from Mac mini" --dry-run
```

如果附近有多副 Frame，可以指定蓝牙名字：

```bash
python examples/send_text.py --name "Frame" --text "Hi"
```

## 4. 做成一个开发者 HUD

把任意标准输入逐行推到眼镜：

```bash
echo "Build succeeded" | python examples/stdin_hud.py
```

也可以把日志、AI 输出、命令结果接进去：

```bash
tail -f /tmp/app.log | python examples/stdin_hud.py --prefix "LOG"
```

```bash
python your_ai_script.py | python examples/stdin_hud.py --prefix "AI"
```

## 5. 直接把命令运行结果投到眼镜

这是目前最适合你 `Mac mini` 场景的脚本：

```bash
python examples/run_with_hud.py --dry-run -- python3 -c "print('tests passed')"
```

接入真实命令时，把 `--dry-run` 去掉即可：

```bash
python examples/run_with_hud.py -- pytest -q
```

如果你想在特定项目目录下运行：

```bash
python examples/run_with_hud.py --cwd /path/to/project -- npm test
```

这个脚本会：

- 在开始时显示当前运行的命令
- 读取子进程的 `stdout` 和 `stderr`
- 自动挑选更重要的行同步到眼镜
- 在结束时显示 `OK` 或 `FAIL <code>`

## 6. Meeting HUD：实时会议字幕原型

先跑演示模式，不需要麦克风：

```bash
python examples/meeting_hud.py --demo --dry-run
```

自定义演示台词：

```bash
python examples/meeting_hud.py --demo --dry-run --demo-lines "meeting starts now|please open the sprint board|ship the frame demo today"
```

查看可用麦克风设备：

```bash
python examples/meeting_hud.py --list-devices
```

开始真实字幕采集：

```bash
python examples/meeting_hud.py --language en --model base
```

如果你想指定某个麦克风：

```bash
python examples/meeting_hud.py --audio-device 0 --language en
```

把字幕顺便落盘：

```bash
python examples/meeting_hud.py --language en --log-file ./logs/meeting.txt
```

常用调参：

- `--duration 3.0`：每 3 秒做一次转写，更像实时字幕
- `--min-rms 0.01`：环境安静时可以调低，避免漏掉轻声说话
- `--model small`：更准但更慢；`base` 更适合先起步
- `--language zh`：如果你要中文会议字幕，建议直接配合下面的 Unicode 模式

## 7. 中文字幕 / Unicode 模式

这条路径基于官方 `text_sprite_block` 示例，宿主端把文本先渲染成位图 sprite，再分片发给 Frame，所以比 `frame.display.text(...)` 更适合中文。

先本地演示：

```bash
python examples/meeting_hud.py --demo --dry-run --render-mode unicode
```

跑中文 demo：

```bash
python examples/meeting_hud.py --demo --dry-run --render-mode unicode --demo-lines "朋友你好，会议现在开始|行动项：本周完成 Frame 原型"
```

跑真实中文字幕：

```bash
python examples/meeting_hud.py --language zh --render-mode unicode
```

如果你想显式指定系统字体：

```bash
python examples/meeting_hud.py --language zh --render-mode unicode --font-family "/System/Library/Fonts/Hiragino Sans GB.ttc"
```

说明：

- `--render-mode auto` 是默认值；当语言是 `zh` 或翻译目标是中文/日文/韩文时，会自动切到 Unicode 模式
- `--font-size`、`--display-width`、`--max-rows` 用来调字幕排版
- 这条路径会上传官方 `data.min.lua`、`text_sprite_block.min.lua`，以及本项目里的 `/Users/jixiangluo/Documents/repository/ai_glasses/examples/frame_apps/text_sprite_block_frame_app.lua`

## 8. 会议翻译 HUD

### 8.1 直接翻成英文

如果源语言不是英文，Whisper 自带 `translate` 任务可以直接翻成英文，不需要额外翻译服务：

```bash
python examples/meeting_hud.py --language zh --translate-to English --render-mode unicode
```

说明：

- 这条路径的真实翻译发生在麦克风音频转写阶段
- `--demo` 模式下，如果你没提供 `--demo-translations`，它只预览布局，不会伪造翻译结果

### 8.2 双语字幕

双语模式会把“原文 + 译文”一起显示，推荐搭配 Unicode 渲染：

```bash
python examples/meeting_hud.py --language zh --translate-to English --bilingual --render-mode unicode
```

如果你只想先预览双语排版：

```bash
python examples/meeting_hud.py --demo --dry-run --bilingual --render-mode unicode --demo-lines "朋友你好，会议现在开始|行动项：本周完成 Frame 原型" --demo-translations "hello everyone, the meeting starts now|action item: finish the frame prototype this week"
```

### 8.3 翻成任意目标语言

如果你想做 `English -> Chinese`、`Chinese -> Japanese` 这类任意目标语言翻译，可以使用 OpenAI 翻译模式：

```bash
export OPENAI_API_KEY="your_key_here"
python examples/meeting_hud.py --language en --translate-to Chinese --translation-provider openai --bilingual --render-mode unicode
```

也可以先用 demo 验证双语显示链路：

```bash
python examples/meeting_hud.py --demo --dry-run --bilingual --render-mode unicode --demo-lines "the design review starts now|please open the sprint board" --demo-translations "设计评审现在开始|请打开冲刺看板"
```

说明：

- `--translation-provider auto` 是默认值
- 当 `--translate-to English` 时，默认走 Whisper 内建翻译
- 当目标语言不是英文时，推荐 `--translation-provider openai`
- OpenAI 模式通过官方 Python SDK 调用 Responses API

## 9. 说话人标签 HUD

这条路径会在字幕前加上 `A:`、`B:` 这类标签，用来提示当前这段话更像是哪位发言人说的。

先本地预览布局，不需要安装 `pyannote`：

```bash
python examples/meeting_hud.py --demo --dry-run --speaker-mode pyannote --demo-lines "今天我们先看设计稿|好的，我来过一下 API 变更|那我补充一下发布时间" --demo-speakers "A|B|A" --render-mode unicode
```

开始真实说话人标签：

```bash
export HUGGINGFACE_TOKEN="your_hf_token"
python examples/meeting_hud.py --language zh --speaker-mode pyannote --render-mode unicode
```

和翻译一起使用：

```bash
export HUGGINGFACE_TOKEN="your_hf_token"
export OPENAI_API_KEY="your_key_here"
python examples/meeting_hud.py --language en --translate-to Chinese --translation-provider openai --bilingual --speaker-mode pyannote --render-mode unicode
```

常用调参：

- `--speaker-model pyannote/speaker-diarization-community-1`：默认模型
- `--speaker-min-seconds 1.0`：只有某位说话人在当前 chunk 内占据足够时长才显示标签
- `--duration 5.0`：块更长时，说话人区分通常更稳定，但实时性会下降

说明：

- 这是按 chunk 做的“当前主说话人”标签，不是完整离线会议分轨
- 对短句、抢话、多人同时说话的场景，标签可能会跳动
- 第一次使用 `pyannote` 前，通常需要在 Hugging Face 页面接受模型条款

## 10. Vision HUD：拍照 -> OCR / 视觉理解 -> 回显

这个脚本支持三种输入源：

- `--source frame`：直接让 Frame 拍一张照
- `--source image`：分析一张本地图片
- `--source demo`：生成一张演示图片，方便先跑通链路

### 10.1 先跑本地 demo

不需要眼镜拍照，先看最终显示效果：

```bash
python examples/vision_hud.py --source demo --analyzer mock --mock-result "识别到桌面上的标签：Frame Vision Demo" --dry-run
```

### 10.2 用 Frame 真机拍照，再做 OCR

```bash
python examples/vision_hud.py --name "Frame 4F" --source frame --analyzer ocr --ocr-language eng
```

如果你想识别中英混合文本：

```bash
python examples/vision_hud.py --name "Frame 4F" --source frame --analyzer ocr --ocr-language chi_sim+eng --render-mode unicode
```

### 10.3 用 OpenAI 做视觉理解

```bash
export OPENAI_API_KEY="your_key_here"
python examples/vision_hud.py --name "Frame 4F" --source frame --analyzer openai --output-language Chinese --render-mode unicode
```

也可以分析本地图片：

```bash
python examples/vision_hud.py --source image --image ./captures/example.jpg --analyzer openai --output-language Chinese --dry-run
```

### 10.4 常用参数

- `--question`：自定义视觉任务，例如“只提取清晰可见的英文单词”
- `--resolution 720`：更高分辨率拍照，通常更利于 OCR
- `--quality-index 4`：最高 JPEG 质量
- `--output-dir ./captures`：保存拍下来的图片
- `--render-mode unicode`：如果结果是中文，建议打开

### 10.5 这条链路怎么工作

- 宿主脚本会把 `/Users/jixiangluo/Documents/repository/ai_glasses/examples/frame_apps/vision_camera_frame_app.lua` 上传到 Frame
- 这个小 Lua app 接收拍照命令并把 JPEG 分片传回 Mac mini
- Mac mini 侧用 `RxPhoto` 拼回完整图片
- 然后本地 OCR 或 OpenAI 视觉分析出一句话
- 最后再把结果推回眼镜显示

## 11. Tap Vision HUD：轻点拍照并分析

这条链路会让 Frame 更像一个真正的可穿戴设备：

- 单击眼镜侧边：拍照、回传、分析
- 双击眼镜侧边：退出 Tap Vision HUD

### 11.1 先本地预览流程

```bash
python examples/tap_vision_hud.py --demo --analyzer mock --mock-result "识别到一张便签纸，上面写着 Frame Vision Demo"
```

如果你想模拟多次单击再双击退出：

```bash
python examples/tap_vision_hud.py --demo --demo-taps "1,1,2" --analyzer mock --mock-result "Detected a demo card on the desk."
```

### 11.2 真机单击拍照 + OCR

```bash
python examples/tap_vision_hud.py --name "Frame 4F" --analyzer ocr --ocr-language eng
```

中英混合 OCR：

```bash
python examples/tap_vision_hud.py --name "Frame 4F" --analyzer ocr --ocr-language chi_sim+eng --render-mode unicode
```

### 11.3 真机单击拍照 + OpenAI 视觉理解

```bash
export OPENAI_API_KEY="your_key_here"
python examples/tap_vision_hud.py --name "Frame 4F" --analyzer openai --output-language Chinese --render-mode unicode
```

### 11.4 这条链路怎么工作

- 宿主脚本会上传 `/Users/jixiangluo/Documents/repository/ai_glasses/examples/frame_apps/tap_vision_frame_app.lua`
- 这个 Lua app 用 `frame.imu.tap_callback(...)` 监听眼镜 tap
- Tap 事件通过官方 `tap` 消息发回 Mac mini
- Mac mini 收到单击后，发送拍照命令并等待 JPEG 回传
- 分析完成后，再把一句结果回显到眼镜

## 12. 这套 starter 适合继续扩展什么

### 会议字幕

- Mac mini 跑 Whisper / 流式 ASR
- 每次取最近一句短字幕
- 调用 `examples/meeting_hud.py` 的逻辑发回 Frame

### 编程副屏

- 监听测试结果、部署状态、CI 日志
- 只把最重要的一行显示到眼镜

### 视觉助手

- Frame 拍照
- Mac mini 做 OCR / VLM 理解
- 只回传一小段摘要到眼镜

## 13. 常见问题

### 连不上蓝牙

- 检查 Frame 已开机且可发现
- 检查 `Terminal` 或 `iTerm` 是否有蓝牙权限
- 离设备近一点，关闭附近重复连接的主机程序

### 会议字幕启动失败

- 检查是否已执行 `pip install -r requirements-meeting.txt`
- 检查是否已执行 `brew install portaudio`
- 首次运行 `faster-whisper` 会下载模型，需要等几分钟

### 翻译模式启动失败

- 检查是否已执行 `pip install -r requirements-translation.txt`
- 如果使用 OpenAI 模式，检查 `OPENAI_API_KEY` 是否已设置
- `whisper` 翻译模式目前只支持输出英文

### 说话人标签启动失败

- 检查是否已执行 `pip install -r requirements-speaker.txt`
- 检查是否已设置 `HUGGINGFACE_TOKEN`
- 检查是否已接受 `pyannote` 模型条款
- 首次加载 `pyannote` 模型会比较慢

### Vision HUD 启动失败

- 检查是否已执行 `pip install -r requirements-vision.txt`
- 如果使用 OCR，确认系统里已安装 `tesseract`
- 如果使用 OpenAI 视觉分析，确认已设置 `OPENAI_API_KEY`
- 如果使用 `--source frame`，确认附近没有别的主机占用眼镜

### Tap Vision HUD 启动失败

- 先用 `python examples/send_text.py --name "Frame 4F" --text "Hello"` 确认基础连接没问题
- 如果轻点没有反应，确认没有别的 Frame app 正在占用 tap 回调
- 如果拍照超时，离近一点并重试，或把 `--capture-timeout` 调大
- 如果你要显示中文结果，建议加 `--render-mode unicode`

### Unicode 字幕不显示

- 检查是否使用了 `--render-mode unicode`
- 检查系统字体是否存在，推荐先试 `/System/Library/Fonts/Hiragino Sans GB.ttc`
- 如果你切回 `plain` 模式，中文基本不会正常显示

### 文字没显示

- 先确保没有别的 Frame 应用占住设备
- 重新运行脚本，让它自动执行 break/reset/break

## 14. 推荐下一步

你可以继续沿这条路线做三个 MVP：

1. `Meeting HUD`：实时字幕
2. `Meeting Translate HUD`：双语会议翻译
3. `Meeting Speaker HUD`：带说话人标签的会议辅助

## 15. 官方资料

- GitHub: <https://github.com/brilliantlabsAR>
- Frame SDK: <https://docs.brilliant.xyz/frame/frame-sdk/>
- Python SDK: <https://docs.brilliant.xyz/frame/frame-sdk/python-sdk/>
- Lua API: <https://docs.brilliant.xyz/frame/frame-sdk/lua-api/>
- Hardware: <https://docs.brilliant.xyz/frame/hardware/>
- OpenAI Responses API quickstart: <https://platform.openai.com/docs/quickstart?api-mode=responses>
- pyannote.audio GitHub: <https://github.com/pyannote/pyannote-audio>
