#介绍
基于阿里云百炼平台声音复刻模型，上传30s音频使您的bot在聊天时使用你的音色聊天，提供对接阿里云的音色一站式创建管理脚本
##使用
- 准备10-30s左右音频，建议存放在插件目录下，在使用脚本时可直接填写文件名
##开始
- 登录
```
https://help.aliyun.com/zh/model-studio/qwen-tts-voice-cloning?spm=a2c4g.11186623.0.0.7bd58e13X9eDUj
```
- 点击主页API文档，选择北京/新加坡创建key
- cd 进入插件目录，python3 aliyun.py
- 创建音色并保存唯一id，并在配置页上传key和id

