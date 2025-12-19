import astrbot.api.message_components as Comp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig
import dashscope
import base64
import hashlib
import subprocess
import os
import asyncio
import random
import time
from dashscope.audio.qwen_tts_realtime import QwenTtsRealtime, QwenTtsRealtimeCallback, AudioFormat

@register("astrbot_plugin_yotts", "梦千秋", "基于百炼平台声音复刻模型，提供完整的音色管理脚本。", "1.0.0")
class VoicePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        dashscope.api_key = config.get("api_key", "")
        self.voice_id = config.get("voice_id", "")
        self.tts_probability = config.get("tts_probability", 50)
        self.max_length = config.get("max_length", 100)
        self.save_audio = config.get("save_audio", False)
        
    @filter.on_decorating_result()
    async def convert_llm_to_tts(self, event: AstrMessageEvent):
        try:
            if self.tts_probability == 0:
                return
                
            result = event.get_result()
            if not result or not result.chain:
                return
                
            text_parts = []
            for component in result.chain:
                if hasattr(component, 'text'):
                    text_parts.append(component.text)
            
            if not text_parts:
                return
                
            llm_text = ''.join(text_parts).strip()
            
            if len(llm_text) < 1:
                return
                
            if len(llm_text) > self.max_length:
                return
                
            if self.tts_probability < 100:
                if random.randint(1, 100) > self.tts_probability:
                    return
            
            wav_file = await self.generate_tts(llm_text)
            
            if wav_file and os.path.exists(wav_file):
                result.chain = [Comp.Record(file=wav_file, url=wav_file)]
                
        except:
            pass
    
    async def generate_tts(self, text):
        try:
            data_dir = self.get_plugin_data_dir()
            
            if self.save_audio:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                wav_file = os.path.join(data_dir, f"tts_{timestamp}.wav")
            else:
                text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
                wav_file = os.path.join(data_dir, f"temp_{text_hash}.wav")
            
            callback = TTSWebSocketCallback(wav_file)
            
            tts = QwenTtsRealtime(
                model='qwen3-tts-vc-realtime-2025-11-27',
                callback=callback,
                url='wss://dashscope.aliyuncs.com/api-ws/v1/realtime'
            )
            
            tts.connect()
            tts.update_session(
                voice=self.voice_id,
                response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                mode='server_commit'
            )
            
            tts.append_text(text)
            tts.finish()
            
            await callback.wait_complete()
            
            if callback.error:
                return None
                
            if not self.save_audio and os.path.exists(wav_file):
                os.remove(wav_file)
                return None
                
            return wav_file
            
        except:
            return None
    
    def get_plugin_data_dir(self):
        current_dir = os.path.dirname(__file__)
        plugin_name = "astrbot_plugin_yotts"
        
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(current_dir)),
            "plugin_data",
            plugin_name
        )
        
        os.makedirs(data_dir, exist_ok=True)
        return data_dir

class TTSWebSocketCallback(QwenTtsRealtimeCallback):
    def __init__(self, wav_file):
        super().__init__()
        self.pcm_data = []
        self.wav_file = wav_file
        self.error = None
        self.complete_event = asyncio.Event()
        
    def on_open(self):
        pass
        
    def on_close(self, code, msg):
        self.save_audio()
        self.complete_event.set()
        
    def on_error(self, error):
        self.error = str(error)
        self.complete_event.set()
        
    def on_event(self, response):
        event_type = response.get('type', '')
        
        if event_type == 'response.audio.delta':
            try:
                audio_chunk = base64.b64decode(response['delta'])
                self.pcm_data.append(audio_chunk)
            except:
                pass
        elif event_type in ['session.finished', 'error']:
            if event_type == 'error':
                self.error = response.get('message', '未知错误')
            self.save_audio()
            self.complete_event.set()
            
    def save_audio(self):
        if not self.pcm_data:
            return
            
        try:
            temp_pcm = f"temp_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}.pcm"
            with open(temp_pcm, 'wb') as f:
                for chunk in self.pcm_data:
                    f.write(chunk)
            
            subprocess.run([
                'ffmpeg', '-y',
                '-f', 's16le', '-ar', '24000', '-ac', '1',
                '-i', temp_pcm,
                self.wav_file
            ], capture_output=True)
            
            if os.path.exists(temp_pcm):
                os.remove(temp_pcm)
                
        except:
            pass
            
    async def wait_complete(self):
        await self.complete_event.wait()