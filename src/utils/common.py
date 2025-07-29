import requests
import json
import threading
import time
import asyncio
import hashlib
from collections import OrderedDict
import concurrent.futures
import queue
import uuid
from config import LIVE_WEB_SEND_URL, GAME_UUID, DONATION_UUID, TTS_CACHE_SIZE, TTS_THROTTLE_INTERVAL
from src.core.tts.manager import init_tts_manager, get_tts_manager
from src.core.utils.util import get_string_no_punctuation_or_emoji
import re
from src.utils.logger import logger

# 异步TTS处理配置
TTS_MAX_CONCURRENT = 3  # 最大并发TTS任务数量
TTS_TASK_TIMEOUT = 10   # 单个TTS任务超时时间（秒）



def filter_content_for_tts(content):
    """
    对弹幕内容进行过滤，判断是否适合生成TTS
    
    Args:
        content: 原始弹幕内容
        
    Returns:
        tuple: (filtered_content, is_valid) - 过滤后的内容和是否有效的标志
    """
    if not content or not isinstance(content, str):
        return "", False
    
    # 1. 首先调用util.py的方法去除首尾标点和表情
    filtered_content = get_string_no_punctuation_or_emoji(content.strip())
    
    # 2. 去除文本表情符号（如 [微笑]、[哭]、[看] 等）
    # 使用正则表达式匹配方括号包围的内容
    filtered_content = re.sub(r'\[[\u4e00-\u9fff\w]+\]', '', filtered_content)
    
    # 3. 去除更多可能影响TTS的标点符号
    # 定义需要完全去除的标点符号
    unwanted_punctuation = "''""\"'`~!@#$%^&*()_+={}[]|\\:;\"<>?/.,，。；：'"
    for punct in unwanted_punctuation:
        filtered_content = filtered_content.replace(punct, '')
    
    # 去除多余的空格
    filtered_content = ' '.join(filtered_content.split())
    
    # 如果过滤后为空，直接返回
    if not filtered_content:
        logger.info(f"内容过滤后为空，跳过TTS: '{content}'")
        return "", False
    
    # 2.1 如果全是数字，跳过
    if filtered_content.isdigit():
        logger.info(f"纯数字内容，跳过TTS: '{content}' -> '{filtered_content}'")
        return "", False
    
    # 2.2 如果长度小于2，跳过
    if len(filtered_content) < 2:
        logger.info(f"内容过短，跳过TTS: '{content}' -> '{filtered_content}'")
        return "", False
    
    # 2.3 其他过滤规则
    
    # 检查是否为纯重复字符（超过4个相同字符）
    if len(set(filtered_content)) == 1 and len(filtered_content) > 4:
        logger.info(f"纯重复字符，跳过TTS: '{content}' -> '{filtered_content}'")
        return "", False
    
    # 检查是否为常见无意义词汇
    meaningless_words = {'呃', '额', '嗯', '啊', '哦', '诶', '哈', '嘿', '咦', '唉', '喔', 'uh', 'um', 'eh', 'ah', 'oh'}
    if filtered_content.lower() in meaningless_words:
        logger.info(f"无意义词汇，跳过TTS: '{content}' -> '{filtered_content}'")
        return "", False
    
    # 检查是否包含告别语
    farewell_words = ['晚安', '再见', '拜拜', '88']
    content_lower = content.lower()
    for farewell in farewell_words:
        if farewell in content_lower:
            logger.info(f"包含告别语，跳过TTS: '{content}' -> 检测到: '{farewell}'")
            return "", False
    
    # 检查是否为URL链接
    url_pattern = r'(https?://|www\.|\.com|\.cn|\.net|\.org)'
    if re.search(url_pattern, filtered_content.lower()):
        logger.info(f"包含URL链接，跳过TTS: '{content}' -> '{filtered_content}'")
        return "", False
    
    # 检查是否为纯英文字母重复（如"aaa", "bbb"）
    if len(filtered_content) >= 3 and filtered_content.isalpha():
        if len(set(filtered_content.lower())) <= 2:  # 最多2种不同字母
            logger.info(f"简单字母重复，跳过TTS: '{content}' -> '{filtered_content}'")
            return "", False
    
    # 检查过长的重复模式（如"哈哈哈哈哈哈"）
    if len(filtered_content) >= 6:
        # 检查是否由某个短模式重复组成
        for pattern_len in range(1, 4):  # 检查1-3字符的重复模式
            if len(filtered_content) % pattern_len == 0:
                pattern = filtered_content[:pattern_len]
                if pattern * (len(filtered_content) // pattern_len) == filtered_content:
                    logger.info(f"重复模式内容，跳过TTS: '{content}' -> '{filtered_content}' (模式: '{pattern}')")
                    return "", False
    
    # 检查是否包含过多数字（超过50%是数字）
    digit_count = sum(1 for c in filtered_content if c.isdigit())
    if len(filtered_content) >= 4 and digit_count / len(filtered_content) > 0.5:
        logger.info(f"数字内容过多，跳过TTS: '{content}' -> '{filtered_content}'")
        return "", False
    
    return filtered_content, True


class TTSCache:
    """TTS音频数据缓存管理器"""
    
    def __init__(self, max_size=100):
        """初始化TTS缓存
        
        Args:
            max_size: 最大缓存条目数量，默认100条
        """
        self.max_size = max_size
        self.cache = OrderedDict()  # 使用有序字典实现LRU缓存
        self._lock = threading.Lock()
    
    def _generate_key(self, content):
        """为文本内容生成缓存键"""
        # 标准化文本内容：去除首尾空白并转小写
        normalized_content = content.strip().lower()
        # 使用MD5生成固定长度的键
        return hashlib.md5(normalized_content.encode('utf-8')).hexdigest()
    
    def get(self, content):
        """从缓存中获取TTS数据
        
        Args:
            content: 文本内容
            
        Returns:
            tuple: (audio_datas, audio_duration, audio_size) 如果存在，否则返回None
        """
        key = self._generate_key(content)
        with self._lock:
            if key in self.cache:
                # 移动到末尾（LRU更新）
                cache_data = self.cache.pop(key)
                self.cache[key] = cache_data
                return cache_data['audio_datas'], cache_data['audio_duration'], cache_data['audio_size']
        return None
    
    def put(self, content, audio_datas, audio_duration, audio_size):
        """将TTS数据存入缓存
        
        Args:
            content: 文本内容
            audio_datas: 音频数据
            audio_duration: 音频时长
            audio_size: 音频大小
        """
        key = self._generate_key(content)
        with self._lock:
            # 如果已存在，先删除
            if key in self.cache:
                del self.cache[key]
            
            # 添加新缓存
            self.cache[key] = {
                'audio_datas': audio_datas,
                'audio_duration': audio_duration,
                'audio_size': audio_size,
                'cached_time': time.time()
            }
            
            # 检查缓存大小限制
            while len(self.cache) > self.max_size:
                # 删除最旧的条目（LRU策略）
                self.cache.popitem(last=False)
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self.cache.clear()
    
    def get_stats(self):
        """获取缓存统计信息"""
        with self._lock:
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'usage_rate': f"{len(self.cache)}/{self.max_size} ({len(self.cache)/self.max_size*100:.1f}%)"
            }


# 全局TTS缓存实例
_tts_cache = TTSCache(max_size=TTS_CACHE_SIZE)


class AsyncTTSManager:
    """异步TTS任务管理器"""
    
    def __init__(self, max_concurrent=TTS_MAX_CONCURRENT):
        self.max_concurrent = max_concurrent
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent)
        self.active_tasks = {}  # 活跃任务字典 {task_id: future}
        self.pending_messages = {}  # 待处理的消息 {task_id: message_info}
        self._lock = threading.Lock()
        
    def submit_tts_task(self, message_id, content, message_data, message_array):
        """提交TTS任务
        
        Args:
            message_id: 消息唯一ID（现在不使用，保持兼容性）
            content: 过滤后的文本内容
            message_data: 原始消息数据
            message_array: 目标消息数组
            
        Returns:
            task_id: 任务ID，如果提交失败返回None
        """
        task_id = str(uuid.uuid4())
        
        with self._lock:
            # 检查是否已经有足够多的任务在运行
            if len(self.active_tasks) >= self.max_concurrent:
                logger.warning(f"🚫 TTS任务队列已满({len(self.active_tasks)}/{self.max_concurrent})，跳过任务 - 内容: {content}")
                return None
            
            # 存储任务信息
            self.pending_messages[task_id] = {
                'content': content,
                'message_data': message_data,
                'message_array': message_array,
                'submit_time': time.time()
            }
            
            # 提交异步任务
            future = self.executor.submit(self._process_tts_task, task_id)
            self.active_tasks[task_id] = future
            
            # 设置任务完成回调
            future.add_done_callback(lambda f: self._task_completed(task_id, f))
            
        logger.info(f"🚀 TTS任务已提交 - 任务ID: {task_id[:8]}, 内容: {content}, 活跃任务数: {len(self.active_tasks)}")
        return task_id
    
    def _process_tts_task(self, task_id):
        """处理单个TTS任务"""
        try:
            task_info = self.pending_messages.get(task_id)
            if not task_info:
                logger.error(f"❌ 找不到任务信息: {task_id}")
                return None
                
            content = task_info['content']
            message_data = task_info['message_data']
            message_array = task_info['message_array']
            
            logger.info(f"🧵 开始处理TTS任务 - 任务ID: {task_id[:8]}, 内容: {content}")
            
            # 检查缓存
            cache_enabled = TTS_CACHE_SIZE > 0
            audio_datas = None
            audio_duration = 0
            audio_size = 0
            
            if cache_enabled:
                cached_result = _tts_cache.get(content)
                if cached_result:
                    audio_datas, audio_duration, audio_size = cached_result
                    logger.info(f"📦 TTS缓存命中 - 任务ID: {task_id[:8]}, 内容: {content}")
                    return self._create_result(message_data, audio_datas, audio_duration, audio_size, 'cached')
            
            # 生成TTS
            if not audio_datas:
                logger.info(f"🔊 开始生成TTS - 任务ID: {task_id[:8]}, 内容: {content}")
                audio_datas, audio_duration, audio_size = self._generate_tts_with_timeout(content)
                
                if audio_datas and cache_enabled:
                    _tts_cache.put(content, audio_datas, audio_duration, audio_size)
                    cache_stats = _tts_cache.get_stats()
                    logger.info(f"💾 TTS缓存已更新 - 任务ID: {task_id[:8]}, 缓存: {cache_stats['usage_rate']}")
            
            if audio_datas:
                logger.info(f"✅ TTS任务完成 - 任务ID: {task_id[:8]}, 内容: {content}, 时长: {audio_duration:.2f}s")
                return self._create_result(message_data, audio_datas, audio_duration, audio_size, 'completed')
            else:
                logger.warning(f"❌ TTS任务失败 - 任务ID: {task_id[:8]}, 内容: {content}")
                return None
                
        except Exception as e:
            logger.error(f"💥 TTS任务异常 - 任务ID: {task_id[:8]}, 错误: {e}")
            import traceback
            logger.error(f"🔍 异常堆栈: {traceback.format_exc()}")
            return None
    
    def _generate_tts_with_timeout(self, content):
        """带超时的TTS生成"""
        try:
            # 获取TTS管理器
            tts_manager = get_tts_manager()
            
            # 在线程中运行异步代码
            async def generate_async():
                return await tts_manager.generate_tts_data(content)
            
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # 设置超时
                return loop.run_until_complete(
                    asyncio.wait_for(generate_async(), timeout=TTS_TASK_TIMEOUT)
                )
            finally:
                loop.close()
                
        except asyncio.TimeoutError:
            logger.warning(f"⏰ TTS生成超时({TTS_TASK_TIMEOUT}秒) - 内容: {content}")
            return None, 0, 0
        except Exception as e:
            logger.error(f"❌ TTS生成异常 - 内容: {content}, 错误: {e}")
            return None, 0, 0
    
    def _create_result(self, message_data, audio_datas, audio_duration, audio_size, tts_status):
        """创建结果对象"""
        return {
            'timestamp': int(time.time() * 1000),
            'data': message_data,
            'audio_datas': audio_datas,
            'audio_duration': audio_duration,
            'audio_size': audio_size,
            'tts_status': tts_status
        }
    
    def _task_completed(self, task_id, future):
        """任务完成回调"""
        try:
            result = future.result()
            task_info = self.pending_messages.get(task_id)
            
            if task_info:
                content = task_info['content']
                message_array = task_info['message_array']
                
                if result and result.get('audio_datas'):
                    # 只有TTS成功且有音频数据时才存储消息
                    with GlobalVal._lock:
                        message_array.insert(0, result)
                        if len(message_array) > GlobalVal.MAX_MESSAGE_COUNT:
                            message_array.pop()
                        logger.info(f"📤 TTS成功，消息已存储 - 内容: {content}, 任务ID: {task_id[:8]}, 数组长度: {len(message_array)}")
                else:
                    # TTS失败或无音频数据，不存储消息
                    logger.warning(f"❌ TTS失败或无音频数据，消息未存储 - 内容: {content}, 任务ID: {task_id[:8]}")
            
        except Exception as e:
            logger.error(f"💥 任务完成处理异常 - 任务ID: {task_id[:8]}, 错误: {e}")
            # 异常情况下不存储任何消息
            task_info = self.pending_messages.get(task_id)
            if task_info:
                content = task_info.get('content', '')
                logger.warning(f"💥 异常情况下，消息未存储 - 内容: {content}, 任务ID: {task_id[:8]}")
        
        finally:
            # 清理任务记录
            with self._lock:
                self.active_tasks.pop(task_id, None)
                self.pending_messages.pop(task_id, None)
                logger.info(f"🧹 任务已清理 - 任务ID: {task_id[:8]}, 剩余活跃任务: {len(self.active_tasks)}")
    
    def get_status(self):
        """获取任务管理器状态"""
        with self._lock:
            return {
                'max_concurrent': self.max_concurrent,
                'active_tasks': len(self.active_tasks),
                'pending_messages': len(self.pending_messages)
            }
    
    def shutdown(self):
        """关闭任务管理器"""
        logger.info("🛑 正在关闭异步TTS管理器...")
        self.executor.shutdown(wait=True)
        logger.info("✅ 异步TTS管理器已关闭")


# 全局异步TTS管理器实例
_async_tts_manager = AsyncTTSManager()


class GlobalVal(object):
    # 点赞总数
    like_num = 0
    # 评论总数
    commit_num = 0
    # 礼物数量和价值
    gift_num = 0
    gift_value = 0
    # 特殊礼物：月下瀑布
    gift_list = []
    # 礼物id列表：礼物去重使用，因为有送一个礼物，但是抖音监听到两个礼物的情况
    gift_id_list = []
    # 记录直播间人数
    member_num = 0
    # 在线观众排名
    rank_user = []
    
    # 消息存储数组，最多保留5条数据
    chat_messages = []  # 普通消息（弹幕）数组
    gift_messages = []  # 礼物消息数组
    like_messages = []  # 点赞消息数组
    member_messages = []  # 成员进入消息数组
    
    # 最大消息保留数量
    MAX_MESSAGE_COUNT = 5
    
    # 线程锁，保护共享数据
    _lock = threading.Lock()
    
    # TTS节流控制
    _last_tts_time = 0  # 上次TTS处理时间戳
    _tts_throttle_interval = TTS_THROTTLE_INTERVAL  # TTS节流间隔（秒）
    
    @classmethod
    def _add_message_to_array(cls, message_array, message_data):
        """向消息数组头部添加新消息，保持最大长度为5"""
        message_with_timestamp = {
            'timestamp': int(time.time() * 1000),  # 毫秒时间戳
            'data': message_data
        }
        # 在数组头部插入新消息
        message_array.insert(0, message_with_timestamp)
        # 保持数组最大长度为5
        if len(message_array) > cls.MAX_MESSAGE_COUNT:
            message_array.pop()  # 移除最旧的消息

    @classmethod
    def _add_chat_message_with_tts_async(cls, message_array, message_data):
        """异步处理TTS的聊天消息添加方法"""
        # 添加处理状态日志
        content_preview = message_data.get('content', '')[:30] if message_data else ''
        logger.info(f"⚡ 进入异步TTS处理流程: {content_preview}")
        
        # TTS节流控制：检查调用频率（基于提交时间，不是完成时间）
        current_time = time.time()
        with cls._lock:
            time_since_last = current_time - cls._last_tts_time
            if time_since_last < cls._tts_throttle_interval:
                logger.info(f"🚫 TTS提交频率限制，跳过处理（距离上次提交 {time_since_last:.2f}s < {cls._tts_throttle_interval}s）- 内容: {content_preview}")
                return
            # 立即更新时间戳，避免短时间内重复提交
            cls._last_tts_time = current_time
            logger.info(f"✅ 通过频率检查，继续处理 - 内容: {content_preview}")
        
        # 对内容进行过滤处理
        content = message_data.get('content', '') if message_data else ''
        if not content or not content.strip():
            logger.info(f"❌ 内容为空，消息被丢弃 - 原始内容: {content}")
            return
            
        logger.info(f"🔍 开始内容过滤 - 原始内容: {content}")
        filtered_content, is_valid = filter_content_for_tts(content)
        if not is_valid:
            logger.info(f"❌ 内容过滤失败，消息被丢弃 - 原始内容: {content}")
            return
        
        content = filtered_content
        logger.info(f"✅ 内容过滤通过 - 过滤后内容: {content}")
        
        # 检查缓存，如果命中则立即存储
        cache_enabled = TTS_CACHE_SIZE > 0
        if cache_enabled:
            cached_result = _tts_cache.get(content)
            if cached_result:
                audio_datas, audio_duration, audio_size = cached_result
                logger.info(f"📦 TTS缓存命中，立即存储消息 - 内容: {content}")
                
                # 创建完整的消息对象并立即存储
                message_with_timestamp = {
                    'timestamp': int(time.time() * 1000),
                    'data': message_data,
                    'audio_datas': audio_datas,
                    'audio_duration': audio_duration,
                    'audio_size': audio_size,
                    'tts_status': 'cached'
                }
                
                with cls._lock:
                    message_array.insert(0, message_with_timestamp)
                    if len(message_array) > cls.MAX_MESSAGE_COUNT:
                        message_array.pop()
                    logger.info(f"💾 缓存消息已存储 - 内容: {content}, 数组长度: {len(message_array)}")
                return
        
        # 异步提交TTS任务（不立即存储消息，等TTS完成后再存储）
        task_id = _async_tts_manager.submit_tts_task(
            message_id=None,  # 不需要消息ID，因为不预先存储
            content=content,
            message_data=message_data,
            message_array=message_array
        )
        
        if task_id:
            logger.info(f"🚀 异步TTS任务已提交，等待完成后存储 - 内容: {content}, 任务ID: {task_id[:8]}")
        else:
            logger.warning(f"⚠️ TTS任务提交失败（队列已满），消息未存储 - 内容: {content}")
            # 任务提交失败，不存储消息


    
    @classmethod
    def update_chat_message(cls, message_data):
        """更新最新的普通消息（异步处理TTS）"""
        # 添加调试日志
        content = message_data.get('content', '') if message_data else ''
        logger.info(f"📝 开始处理弹幕消息: {content}")
        cls._add_chat_message_with_tts_async(cls.chat_messages, message_data)
    
    @classmethod
    def update_gift_message(cls, message_data):
        """更新最新的礼物消息"""
        with cls._lock:
            cls._add_message_to_array(cls.gift_messages, message_data)
    
    @classmethod
    def update_like_message(cls, message_data):
        """更新最新的点赞消息"""
        with cls._lock:
            cls._add_message_to_array(cls.like_messages, message_data)
    
    @classmethod
    def update_member_message(cls, message_data):
        """更新最新的成员进入消息"""
        with cls._lock:
            cls._add_message_to_array(cls.member_messages, message_data)
    
    @classmethod
    def get_latest_chat_message(cls):
        """获取最新的普通消息"""
        with cls._lock:
            return cls.chat_messages[0] if cls.chat_messages else None
    
    @classmethod
    def get_latest_gift_message(cls):
        """获取最新的礼物消息"""
        with cls._lock:
            return cls.gift_messages[0] if cls.gift_messages else None
    
    @classmethod
    def get_latest_like_message(cls):
        """获取最新的点赞消息"""
        with cls._lock:
            return cls.like_messages[0] if cls.like_messages else None
    
    @classmethod
    def get_latest_member_message(cls):
        """获取最新的成员进入消息"""
        with cls._lock:
            return cls.member_messages[0] if cls.member_messages else None
    
    @classmethod
    def get_latest_messages(cls):
        """获取所有最新消息"""
        with cls._lock:
            return {
                'chat': cls.chat_messages[0] if cls.chat_messages else None,
                'gift': cls.gift_messages[0] if cls.gift_messages else None,
                'like': cls.like_messages[0] if cls.like_messages else None,
                'member': cls.member_messages[0] if cls.member_messages else None
            }
    
    @classmethod
    def get_tts_throttle_info(cls):
        """获取TTS节流信息"""
        current_time = time.time()
        with cls._lock:
            time_since_last = current_time - cls._last_tts_time
            return {
                'throttle_interval': cls._tts_throttle_interval,
                'last_tts_time': cls._last_tts_time,
                'time_since_last': time_since_last,
                'can_process_now': time_since_last >= cls._tts_throttle_interval
            }
    
    @classmethod
    def get_async_tts_status(cls):
        """获取异步TTS系统状态"""
        manager_status = _async_tts_manager.get_status()
        cache_stats = _tts_cache.get_stats() if TTS_CACHE_SIZE > 0 else None
        
        return {
            'async_tts_manager': manager_status,
            'cache_stats': cache_stats,
            'throttle_info': cls.get_tts_throttle_info(),
            'config': {
                'max_concurrent': TTS_MAX_CONCURRENT,
                'task_timeout': TTS_TASK_TIMEOUT,
                'cache_size': TTS_CACHE_SIZE,
                'throttle_interval': TTS_THROTTLE_INTERVAL
            }
        }
    
    @classmethod
    def shutdown_async_tts(cls):
        """关闭异步TTS系统"""
        logger.info("🛑 正在关闭异步TTS系统...")
        _async_tts_manager.shutdown()
        logger.info("✅ 异步TTS系统已关闭")


# 初始化全局变量：从服务端获取
def init_global():
    # 初始化 TTS Manager
    try:
        logger.info("正在初始化 TTS Manager...")
        init_tts_manager()
        logger.info("TTS Manager 初始化完成")
    except Exception as e:
        logger.info(f"TTS Manager 初始化失败: {e}")
    
    payload = json.dumps({
        "taskuuid": "querydonation",
        "gameuuid": GAME_UUID
    })
    headers = {
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
        'Content-Type': 'application/json'
    }
    try:
        response = requests.request("POST", LIVE_WEB_SEND_URL, headers=headers, data=payload)
        query_json = response.json()
        game_data = query_json.get("response_data").get("data")
        for data in game_data:
            if data.get("uuid") == DONATION_UUID:
                GlobalVal.like_num = data.get("applypoint")
                GlobalVal.commit_num = data.get("popmsg")
                GlobalVal.gift_value = data.get("giftlist")
                GlobalVal.gift_list = [i for i in data.get("fannamereadylist").split("|") if i]
                return
    except Exception as e:
        logger.info(f"获取线上数据失败：如果你不用将直播数据推送到你们的服务器上，可以忽略此提示")
