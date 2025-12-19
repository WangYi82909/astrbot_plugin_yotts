import sys
import os
import subprocess
import requests
import base64
import pathlib
import threading
import time

def check_and_install():
    """检查并安装依赖"""
    try:
        import dashscope
        from dashscope.audio.qwen_tts_realtime import QwenTtsRealtime, QwenTtsRealtimeCallback, AudioFormat
        import ffmpeg
        print("✓ 依赖检查通过")
        return
    except ImportError as e:
        print(f"✗ 缺少依赖: {e}")
    
    print("正在安装依赖...")
    
    packages = [
        ("requests", "HTTP请求库"),
        ("dashscope>=1.23.9", "阿里云DashScope SDK"),
        ("ffmpeg-python", "FFmpeg Python接口")
    ]
    
    for pkg, desc in packages:
        print(f"正在安装 {desc} ({pkg})...", end=" ", flush=True)
        try:
            # 尝试使用--break-system-packages安装
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg, "--break-system-packages"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("✓ 完成")
            else:
                print(f"✗ 失败: {result.stderr[:100]}")
                # 尝试不使用--break-system-packages
                print("尝试其他安装方式...", end=" ", flush=True)
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    print("✓ 完成")
                else:
                    print(f"✗ 完全失败")
                    sys.exit(1)
        except Exception as e:
            print(f"✗ 安装异常: {str(e)[:50]}")
            sys.exit(1)
    
    print("✓ 所有依赖安装完成")

# 先安装依赖
check_and_install()

# 现在导入模块
import dashscope
from dashscope.audio.qwen_tts_realtime import QwenTtsRealtime, QwenTtsRealtimeCallback, AudioFormat
import ffmpeg

# PCM转MP3
def pcm_to_mp3(pcm_path, mp3_path):
    try:
        (
            ffmpeg
            .input(pcm_path, format='s16le', ar=24000, ac=1)
            .output(mp3_path, codec='libmp3lame', b='128k')
            .overwrite_output()
            .run(quiet=True)
        )
        os.remove(pcm_path)
        return True
    except Exception as e:
        print(f"转码失败: {str(e)}")
        return False

# 回调类
class MyCallback(QwenTtsRealtimeCallback):
    def __init__(self, output_path):
        self.complete_event = threading.Event()
        self.audio_file = open(output_path, "wb")

    def on_close(self, close_status_code, close_msg):
        self.audio_file.close()
        self.complete_event.set()

    def on_event(self, response):
        if response.get('type') == 'response.audio.delta':
            self.audio_file.write(base64.b64decode(response['delta']))
        elif response.get('type') == 'session.finished':
            self.audio_file.close()
            self.complete_event.set()

    def wait_for_finished(self):
        self.complete_event.wait()

# API功能
def create_voice(file_path, target_model, base_url, headers):
    print("正在创建音色...", end=" ", flush=True)
    file_obj = pathlib.Path(file_path)
    data_uri = f"data:audio/mpeg;base64,{base64.b64encode(file_obj.read_bytes()).decode()}"
    payload = {
        "model": "qwen-voice-enrollment",
        "input": {
            "action": "create",
            "target_model": target_model,
            "preferred_name": "custom_voice",
            "audio": {"data": data_uri}
        }
    }
    resp = requests.post(base_url, json=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    print("✓ 完成")
    return resp.json()["output"]["voice"]

def list_voices(base_url, headers):
    print("正在获取音色列表...", end=" ", flush=True)
    payload = {"model": "qwen-voice-enrollment", "input": {"action": "list", "page_size": 100}}
    resp = requests.post(base_url, json=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    print("✓ 完成")
    return resp.json()["output"]["voice_list"]

def delete_voice(voice_name, base_url, headers):
    print(f"正在删除音色 {voice_name}...", end=" ", flush=True)
    payload = {"model": "qwen-voice-enrollment", "input": {"action": "delete", "voice": voice_name}}
    resp = requests.post(base_url, json=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    print("✓ 完成")

def tts_synthesize(voice_id, text, api_key, target_model):
    print("正在合成语音...", end=" ", flush=True)
    os.makedirs("mp3", exist_ok=True)
    timestamp = int(time.time())
    pcm_path = f"mp3/temp_{timestamp}.pcm"
    mp3_path = f"mp3/output_{timestamp}.mp3"
    
    dashscope.api_key = api_key
    callback = MyCallback(pcm_path)
    
    region = api_key[-4:]  # 简单判断区域
    if region == "ffc3":  # 新加坡key
        ws_url = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime"
    else:
        ws_url = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    
    tts = QwenTtsRealtime(
        model=target_model,
        callback=callback,
        url=ws_url
    )
    
    tts.connect()
    tts.update_session(
        voice=voice_id,
        response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
        mode='server_commit'
    )
    tts.append_text(text)
    tts.finish()
    callback.wait_for_finished()
    
    if pcm_to_mp3(pcm_path, mp3_path):
        print("✓ 完成")
        return mp3_path
    print("✗ 转码失败")
    return None

# 主程序
if __name__ == '__main__':
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 50)
    print("阿里云TTS音色管理工具")
    print("=" * 50)
    
    region = input("选择节点（1北京 2新加坡，默认1）：").strip() or "1"
    if region == "1":
        base_url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"
        print("✓ 使用北京节点")
    else:
        base_url = "https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/customization"
        print("✓ 使用新加坡节点")
    
    api_key = input("输入DASHSCOPE API Key：").strip()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    target_model = "qwen3-tts-vc-realtime-2025-11-27"
    
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 50)
        print("阿里云TTS音色管理工具")
        print("=" * 50)
        print("1. 创建音色并合成语音")
        print("2. 查询音色列表")
        print("3. 删除音色")
        print("4. 退出程序")
        print("=" * 50)
        
        choice = input("请选择 (1-4): ").strip()
        
        if choice == "1":
            file_path = input("输入音频文件路径（默认input.mp3）：").strip() or "input.mp3"
            if not os.path.exists(file_path):
                print(f"✗ 文件不存在: {file_path}")
                input("按回车继续...")
                continue
                
            text = input("输入要合成的文字：").strip()
            if not text:
                print("✗ 文字不能为空")
                input("按回车继续...")
                continue
            
            try:
                voice_id = create_voice(file_path, target_model, base_url, headers)
                print(f"✓ 音色ID: {voice_id}")
                output = tts_synthesize(voice_id, text, api_key, target_model)
                if output:
                    print(f"✓ 语音已保存: {output}")
                    print(f"✓ 音色ID: {voice_id}")
            except Exception as e:
                print(f"✗ 操作失败：{str(e)}")
            
            input("按回车继续...")
            
        elif choice == "2":
            try:
                voices = list_voices(base_url, headers)
                print(f"✓ 共有 {len(voices)} 个音色：")
                for idx, v in enumerate(voices, 1):
                    print(f"  {idx}. {v['voice']} - {v['gmt_create']}")
                
                if len(voices) == 0:
                    print("  (无音色)")
            except Exception as e:
                print(f"✗ 操作失败：{str(e)}")
            
            input("按回车继续...")
            
        elif choice == "3":
            try:
                voices = list_voices(base_url, headers)
                if len(voices) == 0:
                    print("✗ 没有可删除的音色")
                    input("按回车继续...")
                    continue
                    
                print(f"请选择要删除的音色 (1-{len(voices)})：")
                for idx, v in enumerate(voices, 1):
                    print(f"  {idx}. {v['voice']}")
                
                try:
                    idx = int(input("序号：").strip()) - 1
                    if 0 <= idx < len(voices):
                        confirm = input(f"确认删除 {voices[idx]['voice']}? (y/n): ").strip().lower()
                        if confirm == 'y':
                            delete_voice(voices[idx]["voice"], base_url, headers)
                            print("✓ 删除成功")
                        else:
                            print("取消删除")
                    else:
                        print("✗ 序号无效")
                except ValueError:
                    print("✗ 请输入数字")
            except Exception as e:
                print(f"✗ 操作失败：{str(e)}")
            
            input("按回车继续...")
            
        elif choice == "4":
            print("退出程序")
            break
        else:
            print("✗ 无效选择，请输入1-4")
            time.sleep(1)