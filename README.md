一款优化Coze返回结果中的图片、语音和网址链接的dow插件，包含以下功能：

+ 提取Coze（包括coze.com和coze.cn）返回的Markdown图片链接中的网址，并修改ReplyType为IMAGE_URL，以便CoW自动下载Markdown链接中的图片；
+ 提取Coze返回的包含 https://s.coze.cn/t/xxx 网址的Markdown链接中的图片网址，并修改ReplyType为IMAGE_URL，以便CoW自动下载Markdown链接中的图片；
+ 识别Coze返回的MP3链接（包括lf-bot-studio-plugin-resource.coze.cn链接），下载为语音文件并作为语音消息发送；
+ 去掉每行结尾的Markdown链接中网址部分的小括号，避免微信误以为")"是网址的一部分导致微信中无法打开该页面。


**安装方法：**

```sh
#installp https://github.com/wangxyd/nicecoze.git
#scanp
```

**配置方法：**

无需任何配置！

**更新方法：**
```sh
#updatep nicecoze
```
