# TTS (Text-to-Speech) 模块

这个模块提供了文本转语音功能，目前支持阿里云TTS服务。

## 模块结构

```
src/core/tts/
├── __init__.py          # 模块初始化文件
├── aliyun.py           # 阿里云TTS提供者实现
├── manager.py          # TTS管理器，负责配置和实例管理
└── README.md           # 本文档
```

## 主要组件

### 1. AliyunTTSProvider (aliyun.py)

阿里云TTS服务的具体实现，包含：
- `AccessToken`: 阿里云访问令牌生成器
- `AliyunTTSProvider`: 阿里云TTS提供者类
- `generate_tts_file`: TTS文件生成函数

### 2. TTSManager (manager.py)

TTS管理器，提供统一的接口：
- 配置文件加载
- TTS提供者初始化
- TTS生成接口
- 状态查询接口

## 使用方法

### 基本使用

```python
from src.core.tts.manager import get_tts_manager

# 获取TTS管理器实例
tts_manager = get_tts_manager()

# 检查TTS是否可用
if tts_manager.is_available():
    # 生成TTS文件
    tts_file = tts_manager.generate_tts("你好，这是一个测试")
    if tts_file:
        print(f"TTS文件生成成功: {tts_file}")
```

### 在HTTP服务器中使用

```python
from src.core.tts.manager import get_tts_manager

# 在接口中使用
@app.route('/api/messages/chat', methods=['GET'])
def get_latest_chat_message():
    # ... 获取消息数据 ...
    
    # 生成TTS
    tts_manager = get_tts_manager()
    tts_file = tts_manager.generate_tts(content)
    
    return jsonify({
        'data': message_data,
        'tts_file': tts_file
    })
```

## 配置要求

在 `config.yaml` 文件中需要配置阿里云TTS相关参数：

```yaml
TTS:
  AliyunTTS:
    type: aliyun
    output_dir: tmp/
    appkey: 你的阿里云appkey
    token: 你的阿里云token
    voice: xiaoyun
    access_key_id: 你的阿里云账号access_key_id  # 可选
    access_key_secret: 你的阿里云账号access_key_secret  # 可选
    # 其他可选配置...
```

## API接口

### TTS状态查询

```
GET /api/tts/status
```

返回TTS服务的状态信息：

```json
{
    "success": true,
    "message": "获取成功",
    "data": {
        "status": "available",
        "provider": "AliyunTTS",
        "voice": "xiaoyun",
        "format": "wav",
        "output_dir": "tts_output"
    }
}
```

### 弹幕消息获取（含TTS）

```
GET /api/messages/chat
```

返回最新弹幕消息并自动生成TTS文件和音频数据：

```json
{
    "success": true,
    "message": "获取成功",
    "data": {
        "content": "弹幕内容",
        // ... 其他消息数据
    },
    "timestamp": 1642780800000,
    "tts_file": "tts_output/chat_tts_20220121_120000_1234.wav",
    "audio_datas": [...],  // 音频数据数组（Opus编码的音频帧）
    "audio_duration": 2.5, // 音频时长（秒）
    "audio_size": 82604    // 音频大小（字节）
}
```

## 特性

- ✅ 支持阿里云TTS服务
- ✅ 自动token管理和刷新
- ✅ 配置文件驱动
- ✅ 单例模式管理
- ✅ 错误处理和日志记录
- ✅ HTTP API集成
- ✅ 文件自动命名和存储
- ✅ 音频数据直接返回（无需文件）
- ✅ JSON序列化支持
- ✅ 音频大小计算和返回
- ✅ 使用现成的 audio_bytes_to_data 方法

## 扩展性

模块设计支持未来添加其他TTS提供者：

1. 在 `src/core/tts/` 目录下创建新的提供者文件（如 `tencent.py`）
2. 实现相同的接口规范
3. 在 `manager.py` 中添加对新提供者的支持
4. 更新配置文件格式

## 注意事项

- 确保阿里云TTS配置正确
- TTS文件会保存在指定的输出目录中
- 建议定期清理旧的TTS文件以节省磁盘空间
- 注意API调用频率限制
