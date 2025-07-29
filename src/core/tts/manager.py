#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS管理器
负责TTS提供者的初始化和管理
"""

import os
import yaml
import logging
from . import create_instance
from src.core.utils.util import audio_bytes_to_data

logger = logging.getLogger(__name__)


class TTSManager:
    """TTS管理器"""
    
    def __init__(self, config_path="config.yaml", output_dir="tts_output"):
        """初始化TTS管理器
        
        Args:
            config_path: 配置文件路径
            output_dir: TTS输出目录
        """
        self.config_path = config_path
        self.output_dir = output_dir
        self.tts_provider = None
        self.config = {}
        self.selected_tts_module = None
        self._load_config()
        self._init_tts_provider()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            self.config = {}
    
    def _init_tts_provider(self):
        """初始化TTS提供者"""
        try:
            # 从配置中获取选择的TTS模块
            self.selected_tts_module = self.config.get('selected_module', {}).get('TTS', 'AliyunTTS')
            logger.info(f"选择的TTS模块: {self.selected_tts_module}")
            
            # 获取TTS配置
            tts_config = self.config.get('TTS', {}).get(self.selected_tts_module, {})
            if not tts_config:
                logger.warning(f"配置文件中未找到 {self.selected_tts_module} 配置，TTS功能将不可用")
                return
            
            # 确保输出目录存在
            os.makedirs(self.output_dir, exist_ok=True)
            
            # 获取TTS类型
            tts_type = tts_config.get('type', 'aliyun')
            
            # 获取delete_audio配置
            delete_audio = str(self.config.get("delete_audio", True)).lower() in ("true", "1", "yes")
            
            # 使用动态创建方式初始化TTS提供者
            self.tts_provider = create_instance(
                tts_type,
                tts_config,
                delete_audio,
            )
            logger.info(f"{self.selected_tts_module} TTS提供者初始化成功")
            
        except Exception as e:
            logger.error(f"初始化TTS提供者失败: {e}")
            self.tts_provider = None
    

    async def generate_tts_data(self, content):
        """生成TTS音频数据

        Args:
            content: 要转换的文本内容

        Returns:
            tuple: (audio_datas, duration, audio_size) 音频数据列表、时长和大小，失败时返回(None, 0, 0)
        """
        if not self.tts_provider:
            logger.warning("TTS提供者未初始化，跳过TTS数据生成")
            return None, 0, 0

        if not content or not content.strip():
            logger.debug("内容为空，跳过TTS数据生成")
            return None, 0, 0

        # 清理内容
        content = content.strip()

        # 过滤掉过短的内容
        if len(content) < 2:
            logger.debug(f"内容过短，跳过TTS数据生成: {content}")
            return None, 0, 0

        try:
            # 生成TTS音频字节数据
            logger.info(f"开始生成TTS音频数据: {content}")
            audio_bytes = await self.tts_provider.text_to_speak(content, None)
            logger.info(f"🔊 TTS提供者返回音频字节，大小: {len(audio_bytes) if audio_bytes else 0} 字节")

            if audio_bytes and isinstance(audio_bytes, bytes):
                # 获取音频文件格式
                audio_format = getattr(self.tts_provider, 'audio_file_type', 'wav')
                logger.info(f"🎵 开始处理音频字节数据，格式: {audio_format}")
                
                # 使用 audio_bytes_to_data 方法处理音频字节数据
                logger.info(f"📊 调用 audio_bytes_to_data 处理音频数据...")
                try:
                    audio_datas, duration = audio_bytes_to_data(audio_bytes, audio_format, is_opus=True)
                    logger.info(f"📊 audio_bytes_to_data 处理完成，duration: {duration}, audio_datas类型: {type(audio_datas)}")
                except Exception as e:
                    logger.error(f"❌ audio_bytes_to_data 处理失败: {e}")
                    import traceback
                    logger.error(f"🔍 audio_bytes_to_data 异常堆栈: {traceback.format_exc()}")
                    return None, 0, 0
                
                if audio_datas:
                    logger.info(f"🔄 开始序列化音频数据，audio_datas类型: {type(audio_datas)}")
                    # 计算音频数据大小并转换为JSON可序列化格式
                    audio_size = 0
                    serializable_audio_datas = []

                    if isinstance(audio_datas, list):
                        logger.info(f"📋 处理list类型音频数据，帧数: {len(audio_datas)}")
                        for i, frame in enumerate(audio_datas):
                            if isinstance(frame, bytes):
                                frame_size = len(frame)
                                audio_size += frame_size
                                logger.debug(f"📦 处理字节帧 {i+1}, 大小: {frame_size} 字节")
                                
                                # 检查帧大小，避免序列化过大的数据
                                if frame_size > 50000:  # 超过50KB的帧
                                    logger.warning(f"⚠️ 字节帧 {i+1} 过大 ({frame_size} 字节)，跳过序列化避免内存问题")
                                    # 对于过大的帧，存储一个标记而不是完整数据
                                    serializable_audio_datas.append(f"<large_frame_{frame_size}_bytes>")
                                else:
                                    # 转换字节为整数列表以便JSON序列化
                                    try:
                                        serializable_audio_datas.append(list(frame))
                                        logger.debug(f"✅ 字节帧 {i+1} 序列化完成")
                                    except MemoryError:
                                        logger.error(f"❌ 字节帧 {i+1} 序列化内存不足，使用占位符")
                                        serializable_audio_datas.append(f"<memory_error_frame_{frame_size}_bytes>")
                                    except Exception as e:
                                        logger.error(f"❌ 字节帧 {i+1} 序列化异常: {e}")
                                        serializable_audio_datas.append(f"<error_frame_{frame_size}_bytes>")
                            elif isinstance(frame, list):
                                audio_size += len(frame)
                                serializable_audio_datas.append(frame)
                                logger.debug(f"📝 处理列表帧 {i+1}, 大小: {len(frame)}")
                            else:
                                # 其他类型转换为字符串
                                frame_str = str(frame)
                                audio_size += len(frame_str)
                                serializable_audio_datas.append(frame_str)
                                logger.debug(f"🔤 处理其他类型帧 {i+1}, 类型: {type(frame)}")
                    elif isinstance(audio_datas, bytes):
                        audio_size = len(audio_datas)
                        logger.info(f"📦 处理bytes类型音频数据，大小: {audio_size} 字节")
                        
                        # 检查bytes大小，避免序列化过大的数据
                        if audio_size > 100000:  # 超过100KB的数据
                            logger.warning(f"⚠️ bytes数据过大 ({audio_size} 字节)，使用占位符避免内存问题")
                            serializable_audio_datas = f"<large_audio_data_{audio_size}_bytes>"
                        else:
                            logger.info(f"🔄 开始转换bytes为列表...")
                            try:
                                # 转换字节为整数列表
                                serializable_audio_datas = list(audio_datas)
                                logger.info(f"✅ bytes数据序列化完成，列表长度: {len(serializable_audio_datas)}")
                            except MemoryError:
                                logger.error(f"❌ bytes数据序列化内存不足，使用占位符")
                                serializable_audio_datas = f"<memory_error_audio_data_{audio_size}_bytes>"
                            except Exception as e:
                                logger.error(f"❌ bytes数据序列化异常: {e}")
                                serializable_audio_datas = f"<error_audio_data_{audio_size}_bytes>"
                    else:
                        logger.info(f"🔤 处理其他类型音频数据: {type(audio_datas)}")
                        # 其他类型直接使用
                        serializable_audio_datas = audio_datas
                        audio_size = len(str(audio_datas))
                    
                    logger.info(f"🎯 音频数据序列化完成，总大小: {audio_size} 字节")

                    logger.info(f"TTS音频数据生成成功，时长: {duration:.2f}秒，大小: {audio_size} 字节")
                    return serializable_audio_datas, duration, audio_size
                else:
                    logger.error(f"❌ 音频数据处理失败: {content}")
                    return None, 0, 0
            else:
                if audio_bytes is None:
                    logger.error(f"❌ TTS提供者返回None: {content}")
                elif not isinstance(audio_bytes, bytes):
                    logger.error(f"❌ TTS提供者返回非bytes数据，类型: {type(audio_bytes)}: {content}")
                else:
                    logger.error(f"❌ TTS音频字节数据生成失败（未知原因）: {content}")
                return None, 0, 0

        except Exception as e:
            logger.error(f"❌ 生成TTS音频数据异常: {e}")
            import traceback
            logger.error(f"🔍 TTS异常堆栈: {traceback.format_exc()}")
            return None, 0, 0
    
    def is_available(self):
        """检查TTS功能是否可用
        
        Returns:
            bool: TTS功能是否可用
        """
        return self.tts_provider is not None
    
    def get_provider_info(self):
        """获取TTS提供者信息
        
        Returns:
            dict: 提供者信息
        """
        if not self.tts_provider:
            return {"status": "unavailable", "provider": None}
        
        return {
            "status": "available",
            "provider": self.selected_tts_module,
            "voice": getattr(self.tts_provider, 'voice', 'unknown'),
            "format": getattr(self.tts_provider, 'format', 'unknown'),
            "output_dir": self.output_dir
        }


# 全局TTS管理器实例
_tts_manager = None


def get_tts_manager(config_path="config.yaml", output_dir="tts_output"):
    """获取TTS管理器实例（单例模式）
    
    Args:
        config_path: 配置文件路径
        output_dir: TTS输出目录
        
    Returns:
        TTSManager: TTS管理器实例
    """
    global _tts_manager
    if _tts_manager is None:
        _tts_manager = TTSManager(config_path, output_dir)
    return _tts_manager


def init_tts_manager(config_path="config.yaml", output_dir="tts_output"):
    """初始化TTS管理器
    
    Args:
        config_path: 配置文件路径
        output_dir: TTS输出目录
        
    Returns:
        TTSManager: TTS管理器实例
    """
    global _tts_manager
    _tts_manager = TTSManager(config_path, output_dir)
    return _tts_manager
