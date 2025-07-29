from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import time
import random
import asyncio
from src.utils.common import GlobalVal, filter_content_for_tts
from src.utils.logger import logger
from src.core.tts.manager import get_tts_manager
from config import CUSTOM_TOPICS, CUSTOM_TOPIC_ENABLED

app = Flask(__name__)
CORS(app)  # 允许跨域访问

# HTTP 服务器配置
HTTP_SERVER_HOST = '0.0.0.0'
HTTP_SERVER_PORT = 8080

# 自定义话题功能状态
_last_returned_message = None  # 上次返回的消息
_custom_topic_index = 0  # 当前话题索引
_custom_topic_lock = threading.Lock()  # 线程锁


def generate_custom_topic_message():
    """生成自定义话题消息并处理TTS"""
    global _custom_topic_index
    
    if not CUSTOM_TOPIC_ENABLED or not CUSTOM_TOPICS:
        return None
    
    with _custom_topic_lock:
        # 循环选择话题
        topic = CUSTOM_TOPICS[_custom_topic_index % len(CUSTOM_TOPICS)]
        _custom_topic_index += 1
    
    # 构造模拟的弹幕消息数据
    fake_message_data = {
        'content': topic,
        'user': {
            'nickName': '系统话题',
            'id': 'system_topic'
        }
    }
    
    try:
        # 对内容进行过滤处理
        filtered_content, is_valid = filter_content_for_tts(topic)
        if not is_valid:
            logger.warning(f"自定义话题内容无效: {topic}")
            return None
        
        logger.info(f"生成自定义话题: {topic}")
        
        # 同步生成TTS
        tts_manager = get_tts_manager()
        audio_datas, audio_duration, audio_size = asyncio.run(tts_manager.generate_tts_data(filtered_content))
        
        if audio_datas:
            # 构造包含TTS数据的完整消息
            message_with_tts = {
                'timestamp': int(time.time() * 1000),
                'data': fake_message_data,
                'audio_datas': audio_datas,
                'audio_duration': audio_duration,
                'audio_size': audio_size,
                'tts_status': 'completed'
            }
            logger.info(f"自定义话题TTS生成成功: {topic}, 音频时长: {audio_duration:.2f}s, 音频大小: {audio_size}字节")
            return message_with_tts
        else:
            logger.warning(f"自定义话题TTS生成失败: {topic}")
            return None
            
    except Exception as e:
        logger.error(f"生成自定义话题消息失败: {e}")
        return None


@app.route('/', methods=['GET'])
def index():
    """API 主页"""
    return jsonify({
        'message': '抖音直播数据 HTTP API 服务',
        'version': '1.0.0',
        'endpoints': {
            '/api/messages/chat': '获取最新的普通消息（弹幕）',
            '/api/messages/gift': '获取最新的礼物消息',
            '/api/messages/like': '获取最新的点赞消息',
            '/api/messages/member': '获取最新的成员进入消息',
            '/api/messages/all': '获取所有类型的最新消息',
            '/api/stats': '获取直播间统计数据',
            '/api/tts/cache': '获取TTS缓存统计信息',
            '/api/tts/cache/clear': '清空TTS缓存',
            '/api/tts/throttle': '获取TTS节流状态信息',
            '/api/custom-topics/status': '获取自定义话题功能状态'
        }
    })


@app.route('/api/messages/chat', methods=['GET'])
def get_latest_chat_message():
    """获取最新的普通消息（弹幕）并生成TTS"""
    global _last_returned_message
    
    # 记录请求开始时间
    request_start_time = time.time()
    
    try:
        message = GlobalVal.get_latest_chat_message()
        
        # 添加调试日志：显示当前消息状态
        if message:
            content = message.get('data', {}).get('content', '')
            timestamp = message.get('timestamp', 0)
            print(f"🌐 API获取到消息 - 内容: {content}, 时间戳: {timestamp}")
        else:
            print(f"🌐 API获取到消息: None（没有可用消息）")
        
        # 检查是否与上次返回的消息相同（通过时间戳判断）
        if message is not None and _last_returned_message is not None:
            if message.get('timestamp') == _last_returned_message.get('timestamp'):
                logger.info(f"[/api/messages/chat] 检测到重复消息，尝试生成自定义话题")
                
                # 生成自定义话题消息
                custom_message = generate_custom_topic_message()
                if custom_message:
                    # 计算总耗时
                    total_duration = (time.time() - request_start_time) * 1000
                    logger.info(f"[/api/messages/chat] 自定义话题返回 - 总耗时: {total_duration:.2f}ms")
                    
                    return jsonify({
                        'success': True,
                        'message': '获取成功（自定义话题）',
                        'data': custom_message['data'],
                        'timestamp': custom_message['timestamp'],
                        'tts_file': None,
                        'audio_datas': custom_message['audio_datas'],
                        'audio_duration': custom_message['audio_duration'],
                        'audio_size': custom_message['audio_size'],
                        'tts_status': custom_message['tts_status'],
                        'is_custom_topic': True
                    }), 200
        
        if message is None:
            # 计算总耗时
            total_duration = (time.time() - request_start_time) * 1000  # 转换为毫秒
            logger.info(f"[/api/messages/chat] 请求完成 - 暂无数据，总耗时: {total_duration:.2f}ms")
            
            return jsonify({
                'success': True,
                'message': '暂无数据',
                'data': None,
                'timestamp': None,
                'tts_file': None,
                'audio_datas': None,
                'audio_duration': 0,
                'audio_size': 0,
                'tts_status': 'none',
                'is_custom_topic': False
            }), 200

        # 直接从消息中获取音频数据（已预生成）
        message_data = message['data']
        audio_datas = message.get('audio_datas')
        audio_duration = message.get('audio_duration', 0)
        audio_size = message.get('audio_size', 0)
        tts_status = message.get('tts_status', 'unknown')
        
        # 记录返回的消息信息
        if message_data and 'content' in message_data:
            content = message_data.get('content', '')
            if content:
                logger.info(f"[/api/messages/chat] 返回弹幕消息 - 内容: '{content[:50]}{'...' if len(content) > 50 else ''}', TTS状态: {tts_status}, 音频时长: {audio_duration:.2f}s, 音频大小: {audio_size}字节")

        # 更新最后返回的消息记录
        _last_returned_message = message
        
        # 计算总耗时
        total_duration = (time.time() - request_start_time) * 1000  # 转换为毫秒
        logger.info(f"[/api/messages/chat] 请求完成 - 总耗时: {total_duration:.2f}ms")

        return jsonify({
            'success': True,
            'message': '获取成功',
            'data': message_data,
            'timestamp': message['timestamp'],
            'tts_file': None,
            'audio_datas': audio_datas,
            'audio_duration': audio_duration,
            'audio_size': audio_size,
            'tts_status': tts_status,
            'is_custom_topic': False
        }), 200
    except Exception as e:
        # 计算总耗时（异常情况）
        total_duration = (time.time() - request_start_time) * 1000  # 转换为毫秒
        logger.error(f"[/api/messages/chat] 请求失败 - 错误: {e}, 总耗时: {total_duration:.2f}ms")
        
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': None,
            'tts_file': None,
            'audio_datas': None,
            'audio_duration': 0,
            'audio_size': 0,
            'tts_status': 'unknown',
            'is_custom_topic': False
        }), 500


@app.route('/api/messages/gift', methods=['GET'])
def get_latest_gift_message():
    """获取最新的礼物消息"""
    try:
        message = GlobalVal.get_latest_gift_message()
        if message is None:
            return jsonify({
                'success': True,
                'message': '暂无数据',
                'data': None
            }), 200
        
        return jsonify({
            'success': True,
            'message': '获取成功',
            'data': message
        }), 200
    except Exception as e:
        logger.error(f"获取最新礼物消息失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@app.route('/api/messages/like', methods=['GET'])
def get_latest_like_message():
    """获取最新的点赞消息"""
    try:
        message = GlobalVal.get_latest_like_message()
        if message is None:
            return jsonify({
                'success': True,
                'message': '暂无数据',
                'data': None
            }), 200
        
        return jsonify({
            'success': True,
            'message': '获取成功',
            'data': message
        }), 200
    except Exception as e:
        logger.error(f"获取最新点赞消息失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@app.route('/api/messages/member', methods=['GET'])
def get_latest_member_message():
    """获取最新的成员进入消息"""
    try:
        message = GlobalVal.get_latest_member_message()
        if message is None:
            return jsonify({
                'success': True,
                'message': '暂无数据',
                'data': None
            }), 200
        
        return jsonify({
            'success': True,
            'message': '获取成功',
            'data': message
        }), 200
    except Exception as e:
        logger.error(f"获取最新成员消息失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@app.route('/api/messages/all', methods=['GET'])
def get_all_latest_messages():
    """获取所有类型的最新消息"""
    try:
        messages = GlobalVal.get_latest_messages()
        return jsonify({
            'success': True,
            'message': '获取成功',
            'data': messages
        }), 200
    except Exception as e:
        logger.error(f"获取所有最新消息失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_live_stats():
    """获取直播间统计数据"""
    try:
        stats = {
            'like_total': GlobalVal.like_num,
            'comment_total': GlobalVal.commit_num,
            'gift_total': GlobalVal.gift_num,
            'gift_value_total': GlobalVal.gift_value,
            'member_count': GlobalVal.member_num,
            'special_gifts': GlobalVal.gift_list,
            'top_users': GlobalVal.rank_user
        }
        return jsonify({
            'success': True,
            'message': '获取成功',
            'data': stats
        }), 200
    except Exception as e:
        logger.error(f"获取直播间统计数据失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@app.route('/api/tts/cache', methods=['GET'])
def get_tts_cache_stats():
    """获取TTS缓存统计信息"""
    try:
        from src.utils.common import _tts_cache
        stats = _tts_cache.get_stats()
        return jsonify({
            'success': True,
            'message': '获取成功',
            'data': stats
        }), 200
    except Exception as e:
        logger.error(f"获取TTS缓存统计失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@app.route('/api/tts/cache/clear', methods=['POST'])
def clear_tts_cache():
    """清空TTS缓存"""
    try:
        from src.utils.common import _tts_cache
        _tts_cache.clear()
        logger.info("TTS缓存已清空")
        return jsonify({
            'success': True,
            'message': 'TTS缓存已清空',
            'data': None
        }), 200
    except Exception as e:
        logger.error(f"清空TTS缓存失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@app.route('/api/tts/throttle', methods=['GET'])
def get_tts_throttle_status():
    """获取TTS节流状态信息"""
    try:
        throttle_info = GlobalVal.get_tts_throttle_info()
        return jsonify({
            'success': True,
            'message': '获取成功',
            'data': throttle_info
        }), 200
    except Exception as e:
        logger.error(f"获取TTS节流状态失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@app.route('/api/tts/async-status', methods=['GET'])
def get_async_tts_status():
    """获取异步TTS系统状态"""
    try:
        status_info = GlobalVal.get_async_tts_status()
        return jsonify({
            'success': True,
            'message': '获取成功',
            'data': status_info
        }), 200
    except Exception as e:
        logger.error(f"获取异步TTS状态失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@app.route('/api/custom-topics/status', methods=['GET'])
def get_custom_topics_status():
    """获取自定义话题功能状态"""
    try:
        global _custom_topic_index, _last_returned_message
        
        with _custom_topic_lock:
            current_index = _custom_topic_index
        
        status_info = {
            'enabled': CUSTOM_TOPIC_ENABLED,
            'topics_count': len(CUSTOM_TOPICS),
            'current_index': current_index,
            'next_topic': CUSTOM_TOPICS[current_index % len(CUSTOM_TOPICS)] if CUSTOM_TOPICS else None,
            'has_last_message': _last_returned_message is not None,
            'topics_list': CUSTOM_TOPICS
        }
        
        return jsonify({
            'success': True,
            'message': '获取成功',
            'data': status_info
        }), 200
    except Exception as e:
        logger.error(f"获取自定义话题状态失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


def start_http_server():
    """启动 HTTP 服务器"""
    try:
        logger.info(f"HTTP API 服务器启动中，地址: http://{HTTP_SERVER_HOST}:{HTTP_SERVER_PORT}")
        print(f"HTTP API 服务器启动中，地址: http://{HTTP_SERVER_HOST}:{HTTP_SERVER_PORT}")
        app.run(host=HTTP_SERVER_HOST, port=HTTP_SERVER_PORT, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"HTTP 服务器启动失败: {e}")
        print(f"HTTP 服务器启动失败: {e}")


def start_http_server_thread():
    """在新线程中启动 HTTP 服务器"""
    server_thread = threading.Thread(target=start_http_server, daemon=True)
    server_thread.start()
    logger.info("HTTP 服务器线程已启动")
    print("HTTP 服务器线程已启动")
    return server_thread


if __name__ == '__main__':
    # 直接运行时启动服务器
    start_http_server() 