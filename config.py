import logging

# 配置日志信息
LOG_FILE_SAVE = True
LOG_FILE_NAME = "log.txt"
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

# 直播信息配置：直播地址，直播用户排名，直播排名抓取间隔，直播推送到后台，推送到后台地址
# LIVE_ROOM_URL = "https://live.douyin.com/211953907443"
LIVE_ROOM_URL = "https://live.douyin.com/497723294501"

# 特殊礼物单独统计
LIVE_GIFT_LIST = ["月下瀑布"]
# 是否抓取在线打赏排名
LIVE_RANK_LIST = True
# 获取礼物排名时间间隔: 建议不要低于10秒
LIVE_RANK_INTERVAL = 10
# 使用ws推送直播数据
LIVE_WEB_SEND = False
# 是否开启HTTP推送
LIVE_HTTP_SEND = True
# 多久向服务端推送一条消息
LIVE_SEND_INTERVAL = 3
# HTTP推送地址：普通用户不用管下面的配置，需要将直播数据推送到你们服务器的才配置
LIVE_WEB_SEND_URL = "http://************/game/gamemgnt"
# 一场比赛唯一的UUID
GAME_UUID = "157ae45b-263b-414a-8976-6d2ad210a7e8"
# 应援UUID(这是我们自己项目推送使用的参数):4
DONATION_UUID = "179019d3-83dd-4619-b7d9-579786659204"

# TTS缓存配置
TTS_CACHE_SIZE = 200  # TTS缓存最大条目数量，设置为0禁用缓存

# TTS节流配置
TTS_THROTTLE_INTERVAL = 1.0  # TTS调用节流间隔（秒），防止弹幕过多时TTS服务器压力过大

# 自定义话题列表配置
CUSTOM_TOPICS = [
    "继续讲解产品如何使用",
    "讲解一下产品功能",
    "为什么要购买防噎仪",
    "水呛到了也可以使用",
    "小孩子能不能用防噎仪",
    "今天购买送了什么",
    "库存紧张了，6件套套装仅有18套，完了后就需要另外购买",
    "会划破喉咙吗",
    "会不会对内脏口腔有伤害"
]
CUSTOM_TOPIC_ENABLED = True  # 是否启用自定义话题功能
