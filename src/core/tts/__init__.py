#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS (Text-to-Speech) 模块
提供文本转语音功能
"""

from .aliyun import TTSProvider
from .edge import TTSProvider as EdgeTTSProvider


__all__ = ['TTSProvider', 'create_instance']


class TTSFactory:
    """TTS 工厂类，用于动态创建不同类型的 TTS 实例"""
    
    @staticmethod
    def create_instance(tts_type, config, delete_audio=True):
        """动态创建 TTS 实例
        
        Args:
            tts_type: TTS 类型 (如 'aliyun', 'doubao', 'edge' 等)
            config: TTS 配置字典
            delete_audio: 是否删除音频文件
            
        Returns:
            TTS 实例对象
        """
        if tts_type == 'aliyun':
            return TTSProvider(config, delete_audio)
        # TODO: 添加其他 TTS 类型的支持
        # elif tts_type == 'doubao':
        #     return DoubaoTTSProvider(config, delete_audio)
        elif tts_type == 'edge':
            return EdgeTTSProvider(config, delete_audio)
        else:
            raise ValueError(f"不支持的 TTS 类型: {tts_type}")


def create_instance(tts_type, config, delete_audio=True):
    """创建 TTS 实例的便捷函数"""
    return TTSFactory.create_instance(tts_type, config, delete_audio)
