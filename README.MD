# 运行步骤

## 安装依赖
```
# 创建虚拟环境
conda remove -n xiaozhi-douyin-live --all -y
conda create -n xiaozhi-douyin-live python=3.10 -y
conda activate xiaozhi-douyin-live

# 添加清华源通道
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge

conda install libopus -y

pip install -r requirements.txt
```

## 修改配置
1. 在 config.py 文件中修改直播间
```
LIVE_ROOM_URL = "https://live.douyin.com/336192654813"
```

2. 在 config.py 文件中修改自定义话题列表（如果没有弹幕，自己找话题说）
```
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
```

## 运行
```
python main.py
```


