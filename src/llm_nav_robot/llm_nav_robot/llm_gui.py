#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM 导航指挥官 —— 独立聊天窗口

功能：
- 聊天框：显示用户指令与小车回复
- 文字输入框 + 发送按钮
- 语音输入按钮：单击开始录音（按钮变为「点击停止录音」），再单击停止并识别发送

通信：发布 /llm_cmd，订阅 /llm_reply（与 llm_commander 节点配合）
用法：ros2 run llm_nav_robot llm_gui
"""

import json
import os
import threading

import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String

import tkinter as tk
from tkinter import scrolledtext

try:
    import sounddevice as sd
    SOUNDDEVICE_OK = True
except Exception:
    SOUNDDEVICE_OK = False

VOSK_MODEL_DIR = os.path.expanduser('~/NL2NAV/models/vosk-model-small-cn-0.22')
SAMPLERATE = 16000

# 界面配色（暗色指挥台）
COLOR_BG = '#1e1e2e'
COLOR_PANEL = '#2a2a3c'
COLOR_INPUT = '#33334a'
COLOR_USER = '#89b4fa'
COLOR_ROBOT = '#a6e3a1'
COLOR_SYS = '#f9e2af'
COLOR_TEXT = '#cdd6f4'
COLOR_BTN = '#45475a'
COLOR_REC = '#f38ba8'


class VoiceRecorder:
    """录音 + vosk 离线中文识别（懒加载模型，无麦克风/无模型时优雅降级）"""

    def __init__(self):
        self.recording = False
        self.frames = []
        self.stream = None
        self.model = None
        self.recog = None
        self.model_error = None

    def _ensure_model(self):
        """首次录音时才加载模型（避免阻塞 GUI 启动）"""
        if self.model is not None:
            return True
        if not SOUNDDEVICE_OK:
            self.model_error = '未安装 sounddevice，语音输入不可用'
            return False
        if not os.path.isdir(VOSK_MODEL_DIR):
            self.model_error = f'未找到语音模型（{VOSK_MODEL_DIR}）'
            return False
        try:
            from vosk import Model, KaldiRecognizer
            self.model = Model(VOSK_MODEL_DIR)
            self.recog = KaldiRecognizer(self.model, SAMPLERATE)
            self.model_error = None
            return True
        except Exception as e:
            self.model_error = f'语音模型加载失败: {e}'
            return False

    def start(self):
        if not SOUNDDEVICE_OK:
            return False, self.model_error or '语音不可用'
        if not self._ensure_model():
            return False, self.model_error or '语音模型不可用'
        try:
            self.frames = []
            self.recording = True
            self.stream = sd.InputStream(samplerate=SAMPLERATE, channels=1,
                                         dtype='int16', callback=self._callback)
            self.stream.start()
            return True, ''
        except Exception as e:
            self.recording = False
            return False, f'无法打开麦克风: {e}'

    def _callback(self, indata, frames, time_info, status):
        if self.recording:
            self.frames.append(indata.copy())

    def stop(self):
        if not self.recording:
            return None, '未在录音'
        self.recording = False
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass
        if not self.frames:
            return None, '未捕获到音频'
        audio = np.concatenate(self.frames)
        try:
            self.recog.Reset()
            self.recog.AcceptWaveform(audio.tobytes())
            text = json.loads(self.recog.FinalResult()).get('text', '').strip()
            if not text:
                return None, '未识别到语音内容'
            return text, ''
        except Exception as e:
            return None, f'识别失败: {e}'


class LLMGui:
    def __init__(self, root):
        self.root = root
        self.root.title('LLM 导航指挥官')
        self.root.configure(bg=COLOR_BG)

        # ---------- ROS 节点（main 中已 rclpy.init）----------
        self.node = rclpy.create_node('llm_gui')
        self.pub = self.node.create_publisher(String, 'llm_cmd', 10)
        self.sub = self.node.create_subscription(String, 'llm_reply',
                                                 self.reply_cb, 10)
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        threading.Thread(target=self.executor.spin, daemon=True).start()

        # ---------- 语音（懒加载）----------
        self.recorder = VoiceRecorder()

        self._build_ui()
        self._fit_screen()
        self.append_chat('系统', 'LLM 导航指挥官已就绪。输入指令，或单击语音按钮说话。')

        # 诊断：2 秒后打印窗口与控件状态（写入 stdout 日志）
        self.root.after(2000, self._dump_geometry)

    # ---------- UI ----------
    def _build_ui(self):
        # 聊天显示区
        self.chat = scrolledtext.ScrolledText(
            self.root, wrap='word', state='disabled',
            bg=COLOR_PANEL, fg=COLOR_TEXT, font=('Noto Sans CJK SC', 11),
            insertbackground=COLOR_TEXT, borderwidth=0)
        self.chat.tag_configure('user', foreground=COLOR_USER)
        self.chat.tag_configure('robot', foreground=COLOR_ROBOT)
        self.chat.tag_configure('sys', foreground=COLOR_SYS)
        self.chat.pack(side='top', fill='both', expand=True, padx=10, pady=(10, 4))

        # 输入区
        self.bottom = tk.Frame(self.root, bg=COLOR_BG)
        self.bottom.pack(side='bottom', fill='x', padx=10, pady=(4, 10))

        self.input_var = tk.StringVar()
        self.entry = tk.Entry(self.bottom, textvariable=self.input_var,
                              bg=COLOR_INPUT, fg=COLOR_TEXT,
                              font=('Noto Sans CJK SC', 12),
                              insertbackground=COLOR_TEXT, relief='flat')
        self.entry.pack(side='left', fill='x', expand=True, ipady=6)
        self.entry.bind('<Return>', lambda e: self.send())

        self.send_btn = tk.Button(self.bottom, text='发送', command=self.send,
                                  bg=COLOR_BTN, fg=COLOR_TEXT,
                                  font=('Noto Sans CJK SC', 11),
                                  relief='flat', padx=14, pady=4,
                                  activebackground='#585b70')
        self.send_btn.pack(side='left', padx=(6, 0))

        self.voice_btn = tk.Button(self.bottom, text='语音输入', command=self.toggle_voice,
                                   bg=COLOR_BTN, fg=COLOR_TEXT,
                                   font=('Noto Sans CJK SC', 11),
                                   relief='flat', padx=14, pady=4,
                                   activebackground='#585b70')
        self.voice_btn.pack(side='left', padx=(6, 0))

        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    def _fit_screen(self):
        """窗口自适应屏幕尺寸并居中"""
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w = min(620, sw - 80)
            h = min(560, sh - 120)
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)
            self.root.geometry(f'{w}x{h}+{x}+{y}')
            self.root.minsize(440, 380)
        except Exception as e:
            self.root.geometry('620x560')

    def _dump_geometry(self):
        """诊断：输出窗口与控件几何信息"""
        try:
            print(f'[GUI诊断] 窗口: {self.root.winfo_geometry()}')
            print(f'[GUI诊断] 屏幕: {self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}')
            for name, w in (('chat', self.chat), ('bottom', self.bottom),
                            ('entry', self.entry), ('send_btn', self.send_btn),
                            ('voice_btn', self.voice_btn)):
                print(f'[GUI诊断] {name}: {w.winfo_geometry()} 映射={w.winfo_ismapped()}')
        except Exception as e:
            print(f'[GUI诊断] 失败: {e}')
        # 定期刷新，观察是否被系统调整
        self.root.after(10000, self._dump_geometry)

    # ---------- 聊天 ----------
    def append_chat(self, who, text):
        self.chat.configure(state='normal')
        tag = {'你': 'user', '小车': 'robot', '系统': 'sys'}.get(who, 'sys')
        self.chat.insert('end', f'{who} > ', tag)
        self.chat.insert('end', f'{text}\n\n', tag)
        self.chat.configure(state='disabled')
        self.chat.see('end')

    def reply_cb(self, msg):
        self.root.after(0, self.append_chat, '小车', msg.data)

    # ---------- 动作 ----------
    def send(self):
        text = self.input_var.get().strip()
        if not text:
            return
        self.input_var.set('')
        self.append_chat('你', text)
        self.pub.publish(String(data=text))

    def toggle_voice(self):
        if self.recorder.recording:
            text, err = self.recorder.stop()
            self.voice_btn.config(text='语音输入', bg=COLOR_BTN)
            if err:
                self.append_chat('系统', err)
            elif text:
                self.append_chat('你', f'[语音] {text}')
                self.pub.publish(String(data=text))
        else:
            ok, err = self.recorder.start()
            if ok:
                self.voice_btn.config(text='点击停止录音', bg=COLOR_REC)
            else:
                self.append_chat('系统', err)

    def on_close(self):
        try:
            if self.recorder.recording:
                self.recorder.stop()
            self.node.destroy_node()
            rclpy.shutdown()
        except Exception:
            pass
        self.root.destroy()


def main(argv=None):
    rclpy.init(args=argv)
    root = tk.Tk()
    LLMGui(root)
    root.mainloop()
    try:
        rclpy.shutdown()
    except Exception:
        pass


if __name__ == '__main__':
    main()
