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
- 做 `Memory HUD`，记住场景/物体并在再次看到时回忆备注
- 做 `Tap Memory HUD`，单击回忆、三击记住、双击退出
- 做 `Voice Command HUD`，直接说“记住这个”“读一下”“翻译成英文”
- 做 `Frame Mic Live HUD`，直接用眼镜自带麦克风做实时转写
- 做 `Agent HUD`，把本机脚本、日志、agent 状态和 CI 结果持续推到眼镜

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

### 一键初始化（推荐）

如果你是在新的 Mac mini 上第一次配置，推荐直接运行：

```bash
./scripts/bootstrap_mac.sh --full
```

如果你只想先装最小运行环境：

```bash
./scripts/bootstrap_mac.sh --minimal
```

这会：

- 检查 Xcode Command Line Tools
- 安装常用 Homebrew 依赖：`portaudio`、`ffmpeg`、`tesseract`
- 创建 `.venv`
- 安装基础依赖和可选能力依赖

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

语音命令依赖：

```bash
pip install -r requirements-voice.txt
```

Agent HUD 指标依赖：

```bash
pip install -r requirements-agent.txt
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

如果你机器上没有 `python` 只有 `python3`，最稳的启动方式是：

```bash
./scripts/run_frame_lab.sh doctor
./scripts/run_frame_lab.sh probe -- --name "Frame EF" --send-text "probe"
```

### Makefile 快捷目标

如果你更习惯 `make`，仓库里也提供了一组高频快捷目标：

```bash
make help
make doctor
make pair-test
make meeting-demo
make vision-demo
make voice-demo
make agent-hud-serve
```

这些目标本质上都是对 `frame_lab.py` 的薄封装。

如果你不想记很多脚本文件名，可以直接用统一入口：

```bash
source .venv/bin/activate
python frame_lab.py scan
python frame_lab.py pair-test -- --text "Hello"
python frame_lab.py say -- --name "Frame 4F" --text "Hello"
python frame_lab.py meeting -- --demo --render-mode unicode
python frame_lab.py vision -- --source demo --analyzer mock --dry-run
python frame_lab.py tap-vision -- --demo
python frame_lab.py memory -- list
python frame_lab.py tap-memory -- --demo
python frame_lab.py voice -- --demo
python frame_lab.py voice-codex -- --demo --dry-run
python frame_lab.py frame-mic-codex -- --demo --dry-run
python frame_lab.py doctor
python frame_lab.py probe -- --name "Frame EF" --send-text "probe"
python frame_lab.py visual-probe -- --name "Frame EF" --duration 15
python frame_lab.py frame-mic -- --duration 5
python frame_lab.py frame-audio-probe -- --name "Frame EF" --duration 4 --transcribe
python frame_lab.py frame-mic-live -- --demo --dry-run
python frame_lab.py agent-hud -- serve --dry-run
python frame_lab.py notify-run -- -- python3 -c "print('tests passed')"
python frame_lab.py showcase
python frame_lab.py task-board -- list
python frame_lab.py voice-codex -- --demo --dry-run
```

说明：

- 第一个参数是子命令，例如 `scan`、`say`、`meeting`
- 子命令后面的参数会原样传给对应脚本
- 如果你想更清楚地区分 launcher 参数和脚本参数，建议加一个 `--`

## 3. 第一次连接测试

如果你遇到“命令没反应”，先跑这个逐步探针：

```bash
python3 frame_lab.py probe -- --name "Frame EF" --send-text "probe"
```

它会明确告诉你：

- 系统蓝牙里是否看得到 `Frame`
- `Bleak` 有没有扫到它
- 是否真正连上了 BLE service
- `break/reset/break` 是否成功
- `send_lua` 是否真正发到了眼镜

如果你想一条命令串跑关键真机链路：

```bash
./scripts/live_connectivity_check.sh --name "Frame EF" --text "probe" --mic-duration 3
```

这会依次执行：

- `probe`
- 真实发字
- 眼镜麦克风录音测试

如果 `probe` 正常，但眼镜上还是只显示 `paired`，再跑这个更强的可视化探针：

```bash
python3 frame_lab.py visual-probe -- --name "Frame EF" --duration 15 --verbose
```

正常情况下，眼镜会持续显示：

- `FRAME CONNECTED`
- `VISUAL PROBE`
- `COUNT 0 / 1 / 2 ...`

如果这一步也没有肉眼可见变化，那就不是“转写没工作”，而是**Frame 端显示接管没有真正发生**。

如果你想先检查本机环境是否适合开发：

```bash
python examples/doctor.py
```

或者使用统一入口：

```bash
python frame_lab.py doctor
```

如果你想一条命令完成“扫描最近设备 + 发测试文字”：

```bash
python examples/pair_and_test.py --text "Hello from Mac mini"
```

或者使用统一入口：

```bash
python frame_lab.py pair-test -- --text "Hello from Mac mini"
```

检查配对的 Frame 是否真的有摄像头和麦克风：

- 摄像头：

```bash
python examples/vision_hud.py --name "Frame 4F" --source frame --analyzer mock --mock-result "Frame camera capture OK" --dry-run
```

- 麦克风：

```bash
python examples/frame_mic_test.py --name "Frame 4F" --duration 5
```

如果你想更明确判断麦克风链路是否正常，可以跑音频探针：

```bash
python examples/frame_audio_probe.py --name "Frame EF" --duration 4 --transcribe

如果你怀疑录音前段有爆点，可以显式调大前导裁剪：

```bash
python examples/frame_audio_probe.py --name "Frame EF" --duration 4 --transcribe --trim-leading 0.3
```
```

它会输出：

- 录音文件路径
- 原始 PCM 时长
- RMS 音量强度
- 可选的转写文本

或者使用统一入口：

```bash
python frame_lab.py vision -- --name "Frame 4F" --source frame --analyzer mock --mock-result "Frame camera capture OK" --dry-run
python frame_lab.py frame-mic -- --name "Frame 4F" --duration 5
```

当前仓库里要注意：

- `/Users/jixiangluo/Documents/repository/ai_glasses/examples/vision_hud.py:198` 走的是 `Frame` 摄像头
- `/Users/jixiangluo/Documents/repository/ai_glasses/examples/meeting_hud.py:185` 和 `/Users/jixiangluo/Documents/repository/ai_glasses/examples/voice_command_hud.py:1` 默认用的是 `Mac mini` 本机麦克风，不是眼镜麦克风

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

## 12. Memory HUD：记住场景，再次看到时提醒

这是一个很适合眼镜的方向：

- 第一次看到某个物体或桌面布局时，保存一条备注
- 下次再次看到类似场景时，自动把备注提示到眼镜上

### 12.1 先保存一条记忆

用 demo 图先体验：

```bash
python examples/memory_hud.py remember --source demo --analyzer mock --mock-result "这是工位上的开发板" --note "这块板子连着 Frame 调试线"
```

也可以直接拍眼镜当前看到的画面：

```bash
python examples/memory_hud.py remember --name "Frame 4F" --source frame --analyzer ocr --ocr-language chi_sim+eng --note "这是会议室门口的 Wi‑Fi 和门禁说明" --show-on-frame
```

### 12.2 回忆最近匹配的记忆

```bash
python examples/memory_hud.py recall --source demo --analyzer mock --mock-result "这是工位上的开发板"
```

真机回忆：

```bash
python examples/memory_hud.py recall --name "Frame 4F" --source frame --threshold 12 --render-mode unicode
```

### 12.3 查看或删除记忆

```bash
python examples/memory_hud.py list
python examples/memory_hud.py forget 1a2b3c4d
```

### 12.4 统一入口

```bash
python frame_lab.py memory -- remember --source demo --analyzer mock --mock-result "桌面有一个 Frame 样机" --note "这是要带去演示的原型"
python frame_lab.py memory -- recall --source demo
```

### 12.5 这条链路怎么工作

- 每张图会生成一个本地感知哈希
- 记忆信息保存在 `/Users/jixiangluo/Documents/repository/ai_glasses/memory/frame_memory.json`
- 回忆时会找最近的图像哈希并判断距离是否足够接近
- 如果没有匹配，就显示当前新场景的简短分析

## 13. Tap Memory HUD：单击回忆，三击记住

这是把 `Memory HUD` 变成可穿戴交互的一步：

- 单击：回忆当前最像的已存场景
- 三击：把当前场景保存成新记忆
- 双击：退出 Tap Memory HUD

### 13.1 先本地预览

```bash
python examples/tap_memory_hud.py --demo
```

默认 demo 会按 `3,1,2` 模拟：

- 先三击保存一条记忆
- 再单击回忆这条记忆
- 最后双击退出

### 13.2 真机运行

```bash
python examples/tap_memory_hud.py --name "Frame 4F" --analyzer ocr --ocr-language chi_sim+eng --render-mode unicode
```

如果你想用 OpenAI 做更强的场景理解：

```bash
export OPENAI_API_KEY="your_key_here"
python examples/tap_memory_hud.py --name "Frame 4F" --analyzer openai --output-language Chinese --render-mode unicode
```

### 13.3 统一入口

```bash
python frame_lab.py tap-memory -- --demo
python frame_lab.py voice -- --demo
python frame_lab.py voice-codex -- --demo --dry-run
python frame_lab.py frame-mic-codex -- --demo --dry-run
python frame_lab.py doctor
python frame_lab.py tap-memory -- --name "Frame 4F" --analyzer ocr --ocr-language chi_sim+eng --render-mode unicode
```

## 14. Voice Command HUD：用语音驱动眼镜功能

这是把你现在所有能力真正串起来的一层：

- 你说“describe this”或“这是什么” -> 拍照并描述场景
- 你说“read this”或“读一下” -> OCR 读取当前文字
- 你说“remember this”或“记住这个” -> 保存当前场景记忆
- 你说“recall this”或“我见过吗” -> 回忆是否见过这个场景
- 你说“translate this to English/Chinese” -> 读取并翻译当前看到的文字
- 你说“exit” -> 退出语音模式

### 14.1 先本地预览

```bash
python examples/voice_command_hud.py --demo --dry-run
```

自定义 demo 命令：

```bash
python examples/voice_command_hud.py --demo --dry-run --demo-commands "help|describe this|remember this as desk prototype|recall this|exit"
```

### 14.2 真机运行

先看麦克风设备：

```bash
python examples/voice_command_hud.py --list-devices
```

开始语音命令模式：

```bash
python examples/voice_command_hud.py --name "Frame 4F" --analyzer ocr --ocr-language chi_sim+eng --render-mode unicode
```

如果你想启用更强的视觉描述和翻译：

```bash
export OPENAI_API_KEY="your_key_here"
python examples/voice_command_hud.py --name "Frame 4F" --analyzer openai --render-mode unicode
```

### 14.3 统一入口

```bash
python frame_lab.py voice -- --demo --dry-run
python frame_lab.py voice -- --name "Frame 4F" --analyzer openai --render-mode unicode
```

## 15. Frame Mic Live HUD：用眼镜自带麦克风实时转写

这条链路和 `Meeting HUD` 的区别是：

- `Meeting HUD` 默认用的是 `Mac mini` 本机麦克风
- `Frame Mic Live HUD` 用的是 **眼镜本体自带麦克风**

### 15.1 先本地预览

```bash
python examples/frame_mic_live_hud.py --demo --dry-run
```

### 15.2 真机实时转写

```bash
python examples/frame_mic_live_hud.py --name "Frame 4F" --language en
```

如果你主要说中文：

```bash
python examples/frame_mic_live_hud.py --name "Frame 4F" --language zh --render-mode unicode

如果你想让它在偶发断连后自动重连：

```bash
python examples/frame_mic_live_hud.py --name "Frame EF" --language zh --render-mode unicode --reconnect
```
```

### 15.3 翻译模式

直接翻成英文：

```bash
python examples/frame_mic_live_hud.py --name "Frame 4F" --language zh --translate-to English
```

翻成中文或其他语言时，推荐 OpenAI：

```bash
export OPENAI_API_KEY="your_key_here"
python examples/frame_mic_live_hud.py --name "Frame 4F" --language en --translate-to Chinese --translation-provider openai --render-mode unicode
```

### 15.4 统一入口

```bash
python frame_lab.py frame-mic-live -- --demo --dry-run
python frame_lab.py agent-hud -- serve --dry-run
python frame_lab.py frame-mic-live -- --name "Frame 4F" --language zh --render-mode unicode
```

### 15.5 调参建议

- `--window-duration 3.0`：每个转写窗口长度
- `--overlap-duration 0.5`：窗口重叠，减轻漏词
- `--min-rms 0.01`：静音阈值
- `--log-file ./logs/frame_mic_live.txt`：把每条转写落盘

## 16. Agent HUD：把本机通知持续推到眼镜

这是最适合开发者日常使用的一层：

- 一个常驻服务保持 `Frame` 连接
- 任何本地脚本都可以通过 HTTP 或标准输入把通知推到眼镜
- 适合接测试结果、部署状态、agent 进度、CI 摘要、日志告警

### 16.1 先用 dry-run 启服务

开一个终端：

```bash
python examples/agent_hud.py serve --dry-run
```

另一个终端发一条通知：

```bash
python examples/agent_hud.py send --text "Tests passed" --level ok
```

### 16.2 真机运行

```bash
python examples/agent_hud.py serve --name "Frame 4F" --render-mode unicode
```

如果你就是想快速做真机实时联调，不想手写循环：

```bash
./scripts/realtime_agent_hud_test.sh --count 10 --interval 1
```

发通知：

```bash
python examples/agent_hud.py send --text "Deploy succeeded" --level ok
python examples/agent_hud.py send --text "Staging warning: slow query" --level warn
```

常驻 pin 一条提醒：

```bash
python examples/agent_hud.py pin --text "Today: stabilize Frame BLE reconnection"
```

清除 pin：

```bash
python examples/agent_hud.py clear
```

### 16.3 直接管道推送

把脚本输出逐行推到眼镜：

```bash
pytest -q | python examples/agent_hud.py pipe --prefix TEST
```

或者：

```bash
python your_agent_script.py | python examples/agent_hud.py pipe --prefix AGENT --level info
```

### 16.3.1 定时轮询命令

如果你想每隔几秒检查一次命令结果，并且只有在输出变化时才提醒：

```bash
python examples/agent_hud.py watch --interval 5 -- -- python3 -c "print('build ok')"
```

把当前输出常驻 pin 到眼镜：

```bash
python examples/agent_hud.py watch --pin-latest --clear-pin-on-exit --interval 10 --name build -- -- python3 -c "print('build ok')"
```

### 16.3.2 直接跟踪日志文件

如果你已经有一个本地日志文件在持续追加：

```bash
python examples/agent_hud.py tail /tmp/app.log --prefix LOG --level warn
```

从文件开头开始读：

```bash
python examples/agent_hud.py tail /tmp/app.log --from-start --max-lines 20
```

### 16.3.3 推系统指标

把 Mac mini 当前系统状态持续推到眼镜：

```bash
python examples/agent_hud.py metrics --interval 5 --pin-latest
```

只跑三次用于测试：

```bash
python examples/agent_hud.py metrics --iterations 3 --interval 1
```

### 16.4 统一入口

```bash
python frame_lab.py agent-hud -- serve --dry-run
python frame_lab.py agent-hud -- send --text "Build succeeded" --level ok
python frame_lab.py agent-hud -- pin --text "Ship the demo"
python frame_lab.py agent-hud -- clear
python frame_lab.py agent-hud -- health
python frame_lab.py agent-hud -- watch -- -- python3 -c "print('build ok')"
python frame_lab.py agent-hud -- tail /tmp/app.log --prefix LOG
python frame_lab.py agent-hud -- metrics --iterations 3 --interval 1
```

### 16.4.1 直接包一层命令

有了 `notify-run` 之后，任何命令都可以自动发开始/关键日志/结束状态通知：

```bash
python examples/notify_run.py -- -- python3 -c "print('tests passed')"
python examples/notify_run.py --name "pytest" -- -- pytest -q
```

如果你想把当前任务常驻 pin 在眼镜上：

```bash
python examples/notify_run.py --pin-running --clear-pin-on-exit --name "pytest" -- -- pytest -q
```

结合统一入口：

```bash
python frame_lab.py notify-run -- -- python3 -c "print('tests passed')"
python frame_lab.py showcase
python frame_lab.py task-board -- list
python frame_lab.py notify-run -- --pin-running --clear-pin-on-exit --name "pytest" -- pytest -q
```

### 16.5 健康检查

服务启动后可查询：

- `GET http://127.0.0.1:8765/health`
- `GET http://127.0.0.1:8765/recent`
- `GET http://127.0.0.1:8765/pinned`

也可以直接用 CLI：

```bash
python examples/agent_hud.py health
python examples/agent_hud.py recent
python examples/agent_hud.py pinned
```

### 16.6 开机常驻（macOS LaunchAgent）

如果你想让 `Agent HUD` 在 Mac mini 上开机常驻：

```bash
./scripts/install_agent_hud_launchagent.sh install --name "Frame 4F"
```

查看状态：

```bash
./scripts/install_agent_hud_launchagent.sh status
```

卸载：

```bash
./scripts/install_agent_hud_launchagent.sh uninstall
```

如果你只是先测试服务链路，不连眼镜：

```bash
./scripts/install_agent_hud_launchagent.sh install --dry-run
```

## 17. Showcase：一条命令串跑核心 demo

如果你想快速演示整个仓库，而不是一个个脚本去敲：

```bash
python examples/showcase.py
```

只看某几个 section：

```bash
python examples/showcase.py --sections meeting,vision,voice
```

列出可用 section：

```bash
python examples/showcase.py --list
```

统一入口：

```bash
python frame_lab.py showcase
python frame_lab.py task-board -- list
```

## 18. Task Board HUD：把当前任务 pin 到眼镜

这层是 `Agent HUD` 的一个自然延伸：

- 本地维护一个轻量任务清单
- 选出当前最重要的任务
- 一键 pin 到眼镜，变成你的“当前焦点”

### 18.1 添加和查看任务

```bash
python examples/task_board_hud.py add --text "Stabilize Frame BLE reconnection" --priority 1 --tag ble
python examples/task_board_hud.py add --text "Polish Vision HUD OCR" --priority 2 --tag vision
python examples/task_board_hud.py list
```

### 18.2 pin 当前最重要任务

先确保 `Agent HUD` 服务在跑：

```bash
python examples/agent_hud.py serve --name "Frame 4F" --render-mode unicode
```

然后 pin：

```bash
python examples/task_board_hud.py pin-next
```

完成后标记 done：

```bash
python examples/task_board_hud.py done 0001
```

清除 pin：

```bash
python examples/task_board_hud.py clear-pin
```

### 18.3 统一入口

```bash
python frame_lab.py task-board -- add --text "Ship the Frame demo" --priority 1
python frame_lab.py task-board -- list
python frame_lab.py task-board -- pin-next
```

## 19. Voice Codex Bridge：语音触发 Codex 和开发命令

这条链路是对你刚才问题的直接回应：

- 说 `doctor` -> 跑环境检查
- 说 `scan frame` -> 扫描眼镜
- 说 `pair test` -> 做连接测试
- 说 `git status` -> 看仓库状态
- 说 `list tasks` / `pin next task` -> 操作任务板
- 说 `run tests` -> 进入确认态，再说 `confirm` 才执行
- 说 `ask codex ...` -> 进入确认态，再说 `confirm` 才直接调用本机 `codex exec`

### 19.1 先本地预览

```bash
python examples/voice_codex_bridge.py --demo --dry-run
```

自定义 demo：

```bash
python examples/voice_codex_bridge.py --demo --dry-run --demo-commands "help|run tests|confirm|ask codex summarize this repo|confirm|exit"
```

### 19.2 真机运行

```bash
python examples/voice_codex_bridge.py --name "Frame EF" --language zh --render-mode unicode
```

如果你希望 `ask codex ...` 执行时更自动：

```bash
python examples/voice_codex_bridge.py --name "Frame EF" --language zh --render-mode unicode --codex-full-auto --codex-ephemeral
```

### 19.3 统一入口

```bash
python frame_lab.py voice-codex -- --demo --dry-run
python frame_lab.py voice-codex -- --name "Frame EF" --language zh --render-mode unicode
```

## 20. Frame Mic Codex Bridge：直接用眼镜麦克风语音控制 Codex

这是目前语音链路最完整的一版：

- 输入源是 **眼镜自带麦克风**
- 输出是 **Codex 和本地开发命令**
- 不再依赖 Mac mini 本机麦克风

### 20.1 先本地预览

```bash
python examples/frame_mic_codex_bridge.py --demo --dry-run
```

高代价命令现在会先提示确认，例如你说 `run tests` 后，需要再说 `confirm`。

### 20.2 真机运行

```bash
python examples/frame_mic_codex_bridge.py --name "Frame EF" --language zh --render-mode unicode

如果你想让它在偶发断连后自动重连：

```bash
python examples/frame_mic_codex_bridge.py --name "Frame EF" --language zh --render-mode unicode --reconnect
```
```

如果你希望 `ask codex ...` 更自动：

```bash
python examples/frame_mic_codex_bridge.py --name "Frame EF" --language zh --render-mode unicode --codex-full-auto --codex-ephemeral
```

### 20.3 统一入口

```bash
python frame_lab.py frame-mic-codex -- --demo --dry-run
python frame_lab.py frame-mic-codex -- --name "Frame EF" --language zh --render-mode unicode
```

## 21. 这套 starter 适合继续扩展什么

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

## 22. 常见问题

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

### Memory HUD 没有匹配到记忆

- 先用 `python examples/memory_hud.py list` 确认本地确实存过记忆
- 把 `--threshold` 调大一些，例如 `16`
- 尽量在相似角度和距离下再次拍摄
- 如果场景变化很大，图像哈希可能会认为这是新场景

### Tap Memory HUD 行为不符合预期

- 单击会回忆，三击会保存，双击会退出
- 如果 tap 经常被合并，试着把 `--tap-threshold` 调小一点
- 如果总是保存成新场景，可以把 `--threshold` 调大一点

### Voice Command HUD 听不清命令

- 先用 `python examples/voice_command_hud.py --list-devices` 确认正确的麦克风设备
- 把 `--listen-duration` 调到 `4.0` 或更高
- 在安静环境下把 `--min-rms` 调低一点，例如 `0.01`
- 如果你主要说中文，建议加 `--language zh`

### Frame Mic Live HUD 没有字幕

- 先用 `python examples/frame_mic_test.py --name "Frame 4F" --duration 5` 确认眼镜麦克风本身可用
- 把 `--window-duration` 调长一点，例如 `4.0`
- 把 `--min-rms` 调低一点，例如 `0.005`
- 如果你要中文显示，建议加 `--render-mode unicode`

### Agent HUD 收不到通知

- 先确认服务端已经运行：`python examples/agent_hud.py serve --dry-run`
- 再用 `python examples/agent_hud.py send --text "ping"` 测一次
- 检查端口是否被占用，默认是 `8765`
- 打开 `http://127.0.0.1:8765/health` 看服务是否存活

### Unicode 字幕不显示

- 检查是否使用了 `--render-mode unicode`
- 检查系统字体是否存在，推荐先试 `/System/Library/Fonts/Hiragino Sans GB.ttc`
- 如果你切回 `plain` 模式，中文基本不会正常显示

### 文字没显示

- 先确保没有别的 Frame 应用占住设备
- 重新运行脚本，让它自动执行 break/reset/break

## 23. 推荐下一步

你可以继续沿这条路线做三个 MVP：

1. `Meeting HUD`：实时字幕
2. `Meeting Translate HUD`：双语会议翻译
3. `Meeting Speaker HUD`：带说话人标签的会议辅助

## 24. 官方资料

- GitHub: <https://github.com/brilliantlabsAR>
- Frame SDK: <https://docs.brilliant.xyz/frame/frame-sdk/>
- Python SDK: <https://docs.brilliant.xyz/frame/frame-sdk/python-sdk/>
- Lua API: <https://docs.brilliant.xyz/frame/frame-sdk/lua-api/>
- Hardware: <https://docs.brilliant.xyz/frame/hardware/>
- OpenAI Responses API quickstart: <https://platform.openai.com/docs/quickstart?api-mode=responses>
- pyannote.audio GitHub: <https://github.com/pyannote/pyannote-audio>

如果你想一条命令完成“扫描最近设备 + 发测试文字”：

```bash
python examples/pair_and_test.py --text "Hello from Mac mini"
```

或者使用统一入口：

```bash
python frame_lab.py pair-test -- --text "Hello from Mac mini"
```

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
