# encoding:utf-8

import re
import requests
import os
import time
import random
from io import BytesIO

import plugins
from bridge.reply import Reply, ReplyType
from common.log import logger
from common.tmp_dir import TmpDir
from plugins import *


@plugins.register(
    name="NiceCoze",
    desire_priority=66,
    hidden=False,
    desc="优化Coze返回结果中的图片、语音和网址链接。",
    version="1.6",
    author="空心菜",
)
class NiceCoze(Plugin):
    def __init__(self):
        super().__init__()
        try:
            self.handlers[Event.ON_DECORATE_REPLY] = self.on_decorate_reply
            self.temp_files = []  # 用于跟踪临时文件
            logger.info("[Nicecoze] inited.")
        except Exception as e:
            logger.warn("[Nicecoze] init failed, ignore.")
            raise e

    def on_decorate_reply(self, e_context: EventContext):
        if e_context["reply"].type != ReplyType.TEXT:
            return
        try:
            channel = e_context["channel"]
            context = e_context["context"]
            content = e_context["reply"].content.strip()
            # 避免图片无法下载时，重复调用插件导致没有响应的问题
            if content.startswith("[DOWNLOAD_ERROR]"):
                return
                
            # 检测是否包含MP3链接并处理
            if 'http' in content and '.mp3' in content:
                logger.debug(f"[Nicecoze] detected possible mp3 link in content={content}")
                voice_reply = self.handle_voice_link(content)
                if voice_reply:
                    logger.info(f"[Nicecoze] sending voice message...")
                    e_context["reply"].content = "[DOWNLOAD_ERROR]\n" + e_context["reply"].content
                    channel.send(voice_reply, context)
                    e_context["reply"] = None
                    e_context.action = EventAction.BREAK_PASS
                    return
            
            # 提取Coze返回的Markdown图片链接中的网址，并修改ReplyType为IMAGE_URL，以便CoW自动下载Markdown链接中的图片
            #if all(x in content for x in ['![', 'http']) and any(x in content for x in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']):
            if 'http' in content and any(x in content for x in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']):
                logger.debug(f"[Nicecoze] starting decorate_markdown_image, content={content}")
                replies = self.decorate_markdown_image(content)
                if replies:
                    logger.info(f"[Nicecoze] sending {len(replies)} images ...")
                    e_context["reply"].content = "[DOWNLOAD_ERROR]\n" + e_context["reply"].content
                    for reply in replies:
                        channel.send(reply, context)
                    #e_context["reply"] = Reply(ReplyType.TEXT, f"{len(replies)}张图片已发送，收到了吗？")
                    # "x张图片已发送，收到了吗？"提示的初衷是告诉我们画/搜了几张图片以及下载/发送失败了几张图片，可以将e_context["reply"]设置为None关闭该提示！
                    e_context["reply"] = None
                    e_context.action = EventAction.BREAK_PASS
                    return
            # 提取Coze返回的包含https://s.coze.cn/t/xxx网址的Markdown链接中的图片网址
            markdown_s_coze_cn = r"([\S\s]*)\!?\[(?P<link_name>.*)\]\((?P<link_url>https\:\/\/s\.coze\.cn\/t\/[\S]*?)\)([\S\s]*)"
            match_obj_s_coze_cn = re.fullmatch(markdown_s_coze_cn, content)
            if match_obj_s_coze_cn and match_obj_s_coze_cn.group('link_url'):
                link_url = match_obj_s_coze_cn.group('link_url')
                logger.info(f"[Nicecoze] match_obj_s_coze_cn found, link_url={link_url}")
                response = requests.get(url=link_url, allow_redirects=False)
                original_url = response.headers.get('Location')
                if response.status_code in [301, 302] and original_url and any(x in original_url for x in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']):
                    logger.info(f"[Nicecoze] match_obj_s_coze_cn found and original_url is a image url, original_url={original_url}")
                    reply = Reply(ReplyType.IMAGE_URL, original_url)
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return
                # 检查重定向后的URL是否为MP3
                elif response.status_code in [301, 302] and original_url and '.mp3' in original_url:
                    logger.info(f"[Nicecoze] match_obj_s_coze_cn found and original_url is an mp3 file, original_url={original_url}")
                    voice_reply = self.download_mp3_file(original_url)
                    if voice_reply:
                        e_context["reply"] = voice_reply
                        e_context.action = EventAction.BREAK_PASS
                        return
                else:
                    logger.info(f"[Nicecoze] match_obj_s_coze_cn found but failed to get original_url or original_url is not a supported media, response.status_code={response.status_code}, original_url={original_url}")
            # 去掉每行结尾的Markdown链接中网址部分的小括号，避免微信误以为")"是网址的一部分导致微信中无法打开该页面
            content_list = content.split('\n')
            new_content_list = [re.sub(r'\((https?://[^\s]+)\)$', r' \1', line) for line in content_list]
            if new_content_list != content_list:
                logger.info(f"[Nicecoze] parenthesis in the url has been removed, content={content}")
                reply = Reply(ReplyType.TEXT, '\n'.join(new_content_list).strip())
                e_context["reply"] = reply
        except Exception as e:
            logger.warn(f"[Nicecoze] on_decorate_reply failed, content={content}, error={e}")
        finally:
            e_context.action = EventAction.CONTINUE

    def handle_voice_link(self, content):
        """处理文本中可能包含的MP3链接"""
        # 匹配独立的MP3链接
        mp3_url_pattern = r"(https?://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(:[0-9]{1,5})?(/[\S]*\.mp3(\?[\S]*)?))"
        mp3_matches = re.findall(mp3_url_pattern, content)
        
        if mp3_matches:
            mp3_url = mp3_matches[0][0]
            logger.info(f"[Nicecoze] Found MP3 URL: {mp3_url}")
            return self.download_mp3_file(mp3_url)
            
        # 匹配Markdown格式的MP3链接
        markdown_mp3_pattern = r"\[(?P<link_name>.*?)\]\((?P<link_url>https?://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(:[0-9]{1,5})?(/[\S]*\.mp3(\?[\S]*)?))(\s.*?)?\)"
        markdown_match = re.search(markdown_mp3_pattern, content)
        
        if markdown_match:
            mp3_url = markdown_match.group('link_url')
            logger.info(f"[Nicecoze] Found MP3 URL in Markdown: {mp3_url}")
            return self.download_mp3_file(mp3_url)
            
        # 特殊处理lf-bot-studio-plugin-resource链接
        coze_voice_pattern = r"(https?://lf-bot-studio-plugin-resource\.coze\.cn/[\S]+?\.mp3(\?[\S]*)?)"
        coze_match = re.search(coze_voice_pattern, content)
        
        if coze_match:
            mp3_url = coze_match.group(0)
            logger.info(f"[Nicecoze] Found Coze MP3 URL: {mp3_url}")
            return self.download_mp3_file(mp3_url)
            
        return None

    def download_mp3_file(self, mp3_url):
        """下载MP3文件并创建语音回复"""
        try:
            # 下载MP3文件
            response = requests.get(mp3_url, timeout=10)
            response.raise_for_status()
            
            # 检查ContentType
            content_type = response.headers.get('Content-Type', '')
            if 'audio' not in content_type and 'application/octet-stream' not in content_type:
                logger.warning(f"[Nicecoze] Content-Type not audio: {content_type}, URL: {mp3_url}")
                # 我们仍然继续，因为有些服务器可能未正确设置Content-Type
            
            # 保存MP3文件
            tmp_dir = TmpDir().path()
            timestamp = int(time.time())
            random_str = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=6))
            mp3_path = os.path.join(tmp_dir, f"nicecoze_voice_{timestamp}_{random_str}.mp3")
            
            with open(mp3_path, "wb") as f:
                f.write(response.content)
            
            if os.path.getsize(mp3_path) == 0:
                logger.error("[Nicecoze] Downloaded voice file size is 0")
                os.remove(mp3_path)
                return None
            
            # 将临时文件添加到跟踪列表
            self.temp_files.append(mp3_path)
            
            logger.info(f"[Nicecoze] Voice download completed: {mp3_path}, size: {os.path.getsize(mp3_path)/1024:.2f}KB")
            
            # 创建语音回复
            reply = Reply()
            reply.type = ReplyType.VOICE
            reply.content = mp3_path
            return reply
            
        except Exception as e:
            logger.error(f"[Nicecoze] Failed to download MP3 file: {e}")
            if 'mp3_path' in locals() and os.path.exists(mp3_path):
                try:
                    os.remove(mp3_path)
                except Exception as clean_error:
                    logger.error(f"[Nicecoze] Error cleaning up failed voice file: {clean_error}")
            return None

    def decorate_markdown_image(self, content):
        # 完全匹配Coze画图的Markdown图片，coze.com对应ciciai.com，coze.cn对应coze.cn
        markdown_image_official = r"([\S\s]*)\!?\[(?P<image_name>.*)\]\((?P<image_url>https\:\/\/\S+?\.(ciciai\.com|coze\.cn)\/[\S]*\.png(\?[\S]*)?)\)([\S\s]*)"
        match_obj_official = re.fullmatch(markdown_image_official, content)
        if match_obj_official and match_obj_official.group('image_url'):
            image_name, image_url = match_obj_official.group('image_name'), match_obj_official.group('image_url')
            logger.info(f"[Nicecoze] markdown_image_official found, image_name={image_name}, image_url={image_url}")
            reply = Reply(ReplyType.IMAGE_URL, image_url)
            return [reply]
        # 完全匹配一张Markdown图片（格式：`![name](url)`）
        markdown_image_single = r"\!\[(?P<image_name>.*)\]\((?P<image_url>https?\:\/\/[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(:[0-9]{1,5})?(\/[\S]*)\.(jpg|jpeg|png|gif|bmp|webp)(\?[\S]*)?)\)"
        match_obj_single = re.fullmatch(markdown_image_single, content, re.DOTALL)
        if match_obj_single and match_obj_single.group('image_url'):
            image_name, image_url = match_obj_single.group('image_name'), match_obj_single.group('image_url')
            logger.info(f"[Nicecoze] markdown_image_single found, image_name={image_name}, image_url={image_url}")
            reply = Reply(ReplyType.IMAGE_URL, image_url)
            return [reply]
        # 匹配多张Markdown图片(格式：`url\n![Image](url)`)
        markdown_image_multi = r"(?P<image_url>https?\:\/\/[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(:[0-9]{1,5})?(\/[\S]*)\.(jpg|jpeg|png|gif|bmp|webp)(\?[\S]*)?)\n*\!\[Image\]\((?P=image_url)\)"
        match_iter_multi = re.finditer(markdown_image_multi, content)
        replies = []
        for match in match_iter_multi:
            image_url = match.group('image_url')
            logger.info(f"[Nicecoze] markdown_image_multi found, image_url={image_url}")
            reply = Reply(ReplyType.IMAGE_URL, image_url)
            replies.append(reply)
        if replies:
            return replies
        if content.startswith('![') and 'http' in content and any(img in content for img in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']):
            logger.info(f"[Nicecoze] it seems markdown image in the content but not matched, content={content}.")

    def cleanup(self):
        """清理插件生成的临时文件"""
        try:
            for file_path in self.temp_files:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.debug(f"[Nicecoze] Cleaned up temp file: {file_path}")
                    except Exception as e:
                        logger.error(f"[Nicecoze] Failed to clean up temp file {file_path}: {e}")
            self.temp_files.clear()
            logger.info("[Nicecoze] Cleanup completed")
        except Exception as e:
            logger.error(f"[Nicecoze] Cleanup task exception: {e}")
            
    def get_help_text(self, **kwargs):
        return "优化Coze返回结果中的图片、语音和网址链接。"
