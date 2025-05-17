import requests
import json
import os
import re
from urllib.parse import urlparse
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TPE1, TIT2, TALB, USLT, SYLT, ID3NoHeaderError
import mimetypes
import logging
import shutil # For file operations

# API 请求地址
API_URL = "https://www.hhlqilongzhu.cn/api/joox/juhe_music.php"

# 音频文件下载目录 - 修改为 Flask 的 static 子目录
# 注意：在 Flask 应用中，通常我们会使用 current_app.root_path 来构建绝对路径
# 但在这个模块中，我们暂时定义一个相对路径，由调用方 (app.py) 处理成绝对路径
DOWNLOAD_DIR_NAME = "downloads" # 将在此目录下按 歌手/专辑/歌曲名 存放
TEMP_DIR_NAME = "temp" # 临时文件存放

# Regex to parse [mm:ss.xx] or [mm:ss] timestamps
TIMESTAMP_REGEX = re.compile(r'\[(\d{2}):(\d{2})\.?(\d{2,3})?\]') # Allow 2 or 3 digits for ms

# 设置基本的日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---
def _sanitize_filename(filename):
    """
    Sanitizes a string to be a valid filename by removing or replacing illegal characters.
    """
    sanitized = re.sub(r'[\\/*?:"<>|]', "", filename)
    sanitized = re.sub(r'\s+', " ", sanitized).strip()
    # Limit length if necessary (optional, common for filesystems)
    # max_len = 200
    # if len(sanitized) > max_len:
    #     name, ext = os.path.splitext(sanitized)
    #     sanitized = name[:max_len - len(ext)] + ext
    return sanitized

def _clean_api_title_source(title_str):
    """
    Removes source indicators like [酷我], [网易] from API titles.
    Example: "Song Title [酷我]" -> "Song Title"
    """
    if isinstance(title_str, str):
        cleaned_title = re.sub(r'\s*\[[^\]]+\]$', '', title_str).strip()
        if '[' in cleaned_title and ']' in cleaned_title:
             cleaned_title = cleaned_title.rsplit('[', 1)[0].strip()
        return cleaned_title
    return title_str

def parse_lrc_line(line):
    """
    Parses a single LRC format lyric line to extract timestamp and text.
    Returns a tuple (timestamp_in_ms, text) or None if parsing fails.
    Timestamp is converted to milliseconds.
    """
    match = TIMESTAMP_REGEX.match(line)
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        ms_str = match.group(3)

        milliseconds = 0
        if ms_str:
            if len(ms_str) == 2:
                milliseconds = int(ms_str) * 10
            elif len(ms_str) == 3:
                milliseconds = int(ms_str)
        
        timestamp_ms = (minutes * 60 + seconds) * 1000 + milliseconds
        text_start_index = line.rfind(']') + 1
        text = line[text_start_index:].strip()
        return (timestamp_ms, text)
    return None

# --- API Interaction Functions ---
def request_api(params):
    """
    发送API请求并处理基本错误。
    Returns: response JSON or None if error.
    """
    try:
        response = requests.get(API_URL, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP错误: {e.response.status_code} - {e}")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"请求错误: {e}")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"解析API响应失败: 返回的不是有效的JSON. Error: {e}")
        # logging.debug(f"原始响应内容: {response.text[:500]}...") # For debugging
        return None
    except Exception as e:
        logging.error(f"处理API请求时发生未知错误: {e}")
        return None

def search_music(query):
    """
    根据关键词搜索歌曲列表。
    Returns: list of songs or None.
    """
    params = {'msg': query, 'type': 'json'}
    data = request_api(params)

    if isinstance(data, list) and data:
        songs = []
        for item in data:
            index = item.get('n')
            title = item.get('title', '未知标题')
            singer = item.get('singer', '未知歌手')
            title = _clean_api_title_source(title)
            if index is not None:
                songs.append({'index': index, 'title': title, 'singer': singer})
        return songs if songs else None
    elif isinstance(data, list) and not data:
        logging.info("API返回了空列表，未搜索到歌曲。")
        return None
    else:
        if data is not None:
             logging.error("搜索结果格式不正确 (预期列表)。")
        # Further error details logged by request_api
        return None

def get_song_details(query, song_number):
    """
    根据关键词和歌曲序号获取歌曲详细信息。
    Returns: song details dict or None.
    """
    params = {'msg': query, 'n': song_number, 'type': 'json'}
    data = request_api(params)

    if isinstance(data, dict) and 'data' in data:
        details_data = data['data']
        if isinstance(details_data, list) and details_data:
            details_data = details_data[0]
        
        if isinstance(details_data, dict) and details_data.get('code') == 200:
             if 'title' in details_data:
                 details_data['title'] = _clean_api_title_source(details_data['title'])
             return details_data
        else:
            logging.error(f"获取歌曲详情失败。API返回代码: {details_data.get('code') if isinstance(details_data, dict) else '未知'}。")
            return None
    else:
        if data is not None:
            logging.error("获取歌曲详情失败: 顶层响应格式不正确。")
        # Further error details logged by request_api
        return None

# --- File Handling and Metadata Embedding ---
def download_file_to_path(url, file_path, is_cover=False):
    """
    下载文件到指定路径。
    Returns: True if download successful, False otherwise.
    """
    try:
        # Use a specific user-agent, some servers might block default requests user-agent
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        timeout = 15 if is_cover else 60 # Shorter timeout for cover, longer for audio
        response = requests.get(url, stream=True, timeout=timeout, headers=headers)
        response.raise_for_status()
        os.makedirs(os.path.dirname(file_path), exist_ok=True) # Ensure directory exists
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logging.info(f"文件成功下载到: {file_path}")
        return True
    except requests.exceptions.HTTPError as e:
        logging.error(f"下载文件HTTP错误 ({file_path}): {e.response.status_code} - {e}")
        return False
    except requests.exceptions.RequestException as e:
        logging.error(f"下载文件失败 ({file_path}): {e}")
        return False
    except IOError as e:
        logging.error(f"保存文件失败 ({file_path}): {e}")
        return False
    except Exception as e:
        logging.error(f"下载或保存文件时发生未知错误 ({file_path}): {e}")
        return False

def embed_metadata(audio_file_path, song_details, temp_cover_path=None):
    """
    将元数据嵌入到MP3文件。
    """
    try:
        try:
            audio = MP3(audio_file_path, ID3=ID3)
        except ID3NoHeaderError:
            audio = MP3(audio_file_path)
            audio.add_tags()
        
        if audio.tags is None:
            audio.tags = ID3()
        elif not isinstance(audio.tags, ID3):
            audio.tags = ID3()

        title_for_id3 = _clean_api_title_source(song_details.get('title', 'Unknown Title'))
        singer_for_id3 = song_details.get('singer', 'Unknown Artist')

        audio.tags.delall('TIT2')
        audio.tags.add(TIT2(encoding=3, text=title_for_id3))
        logging.info(f"已嵌入标题: {title_for_id3}")

        audio.tags.delall('TPE1')
        audio.tags.add(TPE1(encoding=3, text=singer_for_id3))
        logging.info(f"已嵌入艺术家: {singer_for_id3}")

        lyric_text = song_details.get('lyric')
        if lyric_text and isinstance(lyric_text, str):
            logging.info("找到歌词数据，尝试嵌入 SYLT 帧...")
            audio.tags.delall('SYLT')
            sylt_frames_data = []
            lines = lyric_text.strip().split('\n')
            for line in lines:
                parsed_line = parse_lrc_line(line)
                if parsed_line:
                    timestamp_ms, text = parsed_line
                    sylt_frames_data.append((text, timestamp_ms))
            
            if sylt_frames_data:
                try:
                    audio.tags.add(SYLT(encoding=3, lang='und', format=2, type=1, desc='Lyrics', text=sylt_frames_data))
                    logging.info(f"已添加 {len(sylt_frames_data)} 行同步歌词 (SYLT)。")
                except Exception as e_sylt:
                    logging.warning(f"嵌入 SYLT 失败: {e_sylt}. 尝试 USLT 作为备选。")
                    audio.tags.delall('USLT') # Clean up before fallback
                    audio.tags.add(USLT(encoding=3, lang='und', desc='Lyrics', text=lyric_text))
                    logging.info("已将原始歌词作为非同步歌词 (USLT) 嵌入。")
            else:
                logging.info("未能从歌词数据中解析出有效的带时间戳的歌词行，尝试 USLT。")
                audio.tags.delall('USLT')
                audio.tags.add(USLT(encoding=3, lang='und', desc='Lyrics', text=lyric_text))
                logging.info("已将原始歌词作为非同步歌词 (USLT) 嵌入。")
        else:
            logging.info("没有找到歌词数据或歌词为空，跳过歌词嵌入。")

        if temp_cover_path and os.path.exists(temp_cover_path):
            logging.info("找到封面图片，尝试嵌入 APIC 帧...")
            mime_type, _ = mimetypes.guess_type(temp_cover_path)
            if mime_type is None:
                 mime_type = 'image/jpeg' 
            try:
                with open(temp_cover_path, 'rb') as f:
                    cover_data = f.read()
                audio.tags.delall('APIC') 
                audio.tags.add(APIC(encoding=0, mime=mime_type, type=3, desc='Cover', data=cover_data))
                logging.info(f"已添加封面图片 (APIC) 类型: {mime_type}。")
            except Exception as e_apic:
                logging.error(f"嵌入封面图片失败: {e_apic}")
        else:
            logging.info("没有找到封面图片或下载失败，跳过封面嵌入。")

        audio.save(v1=0, v2_version=3)
        logging.info(f"元数据嵌入完成。文件: {audio_file_path}")
        return True

    except Exception as e:
        logging.error(f"嵌入元数据时发生错误 ({audio_file_path}): {e}")
        # import traceback # For detailed debugging in a dev environment
        # traceback.print_exc()
        return False
    finally:
        if temp_cover_path and os.path.exists(temp_cover_path):
            try:
                os.remove(temp_cover_path)
                logging.info(f"已删除临时封面文件: {temp_cover_path}")
            except OSError as e:
                logging.error(f"删除临时封面文件失败: {e}")

def download_song_assets_for_web(song_details, app_static_folder):
    """
    下载歌曲音频文件、封面，并将元数据嵌入音频文件。
    专为 Flask Web 应用设计，文件保存在 app_static_folder 下。
    Args:
        song_details (dict): 包含歌曲信息的字典。
        app_static_folder (str): Flask App 的 static 文件夹绝对路径。
    Returns:
        tuple: (relative_audio_path, success, error_message)
               relative_audio_path 是相对于 static 文件夹的路径，例如 'downloads/song.mp3'
               success 是布尔值
               error_message 是字符串或 None
    """
    audio_url = song_details.get('url')
    title = song_details.get('title', '未知歌名') # 应该已经被 get_song_details 清理
    singer = song_details.get('singer', '未知歌手')
    cover_url = song_details.get('cover')

    if not audio_url:
        logging.error("歌曲播放链接不存在，无法下载音频。")
        return None, False, "歌曲播放链接不存在"

    # 构建在 static 文件夹下的下载和临时目录的绝对路径
    # 例如: /path/to/your/app/static/downloads
    download_target_dir = os.path.join(app_static_folder, DOWNLOAD_DIR_NAME)
    # 例如: /path/to/your/app/static/temp
    temp_processing_dir = os.path.join(app_static_folder, TEMP_DIR_NAME) 

    os.makedirs(download_target_dir, exist_ok=True)
    os.makedirs(temp_processing_dir, exist_ok=True)

    base_filename_unsafe = f"{title} - {singer}"
    base_filename_safe = _sanitize_filename(base_filename_unsafe)

    # 临时音频文件使用随机名称，存放在 app_static_folder/temp/
    temp_audio_filename_random = f"temp_audio_{os.urandom(8).hex()}" # 无扩展名
    # 完整临时音频文件路径，先不带扩展名
    temp_audio_file_path_no_ext = os.path.join(temp_processing_dir, temp_audio_filename_random)
    
    # 最终和临时音频文件的完整路径（带扩展名），稍后确定
    temp_audio_file_path_with_ext = None
    final_audio_filename_with_ext = None
    final_audio_full_path = None
    relative_final_audio_path = None # 相对于 static 的路径，用于网页引用

    logging.info(f"准备下载: {title} - {singer}")

    try:
        logging.info(f"正在下载音频文件从: {audio_url} ...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(audio_url, stream=True, timeout=60, headers=headers)
        response.raise_for_status()

        audio_file_extension = '.mp3' # Default
        content_type = response.headers.get('Content-Type', '').lower()
        parsed_url_path = urlparse(audio_url).path
        
        path_basename = os.path.basename(parsed_url_path)
        if '.' in path_basename:
            ext_from_url = os.path.splitext(path_basename)[1].lower()
            if ext_from_url in ['.mp3', '.m4a', '.aac', '.flac', '.wav', '.ogg']:
                audio_file_extension = ext_from_url
        elif 'audio/mpeg' in content_type or 'mp3' in content_type:
            audio_file_extension = '.mp3'
        elif 'audio/aac' in content_type:
            audio_file_extension = '.aac'
        elif 'audio/mp4' in content_type or 'm4a' in content_type: 
            audio_file_extension = '.m4a'
        elif 'audio/flac' in content_type or 'x-flac' in content_type:
            audio_file_extension = '.flac'
        elif 'audio/wav' in content_type or 'x-wav' in content_type:
            audio_file_extension = '.wav'
        
        temp_audio_file_path_with_ext = temp_audio_file_path_no_ext + audio_file_extension
        final_audio_filename_with_ext = f"{base_filename_safe}{audio_file_extension}"
        final_audio_full_path = os.path.join(download_target_dir, final_audio_filename_with_ext)
        
        # 用于网页引用的相对路径: e.g., downloads/song.mp3
        relative_final_audio_path = os.path.join(DOWNLOAD_DIR_NAME, final_audio_filename_with_ext).replace('\\', '/')

        if os.path.exists(final_audio_full_path):
            logging.info(f"最终音频文件 '{final_audio_filename_with_ext}' 已存在于 {download_target_dir}，跳过下载。")
            # 如果文件已存在，我们依然需要返回其相对路径供播放器使用
            return relative_final_audio_path, True, f"文件已存在: {final_audio_filename_with_ext}"

        with open(temp_audio_file_path_with_ext, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logging.info(f"音频文件下载完成到临时路径: {temp_audio_file_path_with_ext}")

    except requests.exceptions.HTTPError as e:
        msg = f"下载音频文件HTTP错误: {e.response.status_code} - {e}"
        logging.error(msg)
        return None, False, msg
    except requests.exceptions.RequestException as e:
        msg = f"下载音频文件时发生请求错误: {e}"
        logging.error(msg)
        return None, False, msg
    except IOError as e:
        msg = f"保存临时音频文件时发生IO错误: {e}"
        logging.error(msg)
        return None, False, msg
    except Exception as e:
        msg = f"下载音频文件时发生未知错误: {e}"
        logging.error(msg)
        if temp_audio_file_path_with_ext and os.path.exists(temp_audio_file_path_with_ext):
            try: os.remove(temp_audio_file_path_with_ext) 
            except OSError: pass
        return None, False, msg

    # --- Cover Download (to temp_processing_dir) ---
    temp_cover_full_path = None
    if cover_url:
        cover_ext = os.path.splitext(urlparse(cover_url).path)[1].lower()
        if not cover_ext or cover_ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            cover_ext = '.jpg'
        temp_cover_filename = f"temp_cover_{os.urandom(8).hex()}{cover_ext}"
        temp_cover_full_path = os.path.join(temp_processing_dir, temp_cover_filename)
        logging.info(f"正在下载封面: {title} - {singer} 到 {temp_cover_full_path}...")
        if not download_file_to_path(cover_url, temp_cover_full_path, is_cover=True):
            logging.warning(f"封面文件下载失败: {cover_url}")
            temp_cover_full_path = None # Ensure it's None if download fails
    
    # --- Metadata Embedding (if MP3 and audio downloaded) ---
    if os.path.exists(temp_audio_file_path_with_ext) and audio_file_extension == '.mp3':
        logging.info(f"开始为 {temp_audio_file_path_with_ext} 嵌入元数据...")
        embed_metadata_success = embed_metadata(temp_audio_file_path_with_ext, song_details, temp_cover_full_path)
        if not embed_metadata_success:
            logging.warning(f"元数据嵌入可能未完全成功: {temp_audio_file_path_with_ext}")
            # 继续移动文件，即使元数据嵌入失败
    elif audio_file_extension != '.mp3':
        logging.info(f"下载的文件类型为 {audio_file_extension}，当前仅支持为 .mp3 文件嵌入元数据。")
    
    # --- Move/Rename temp audio file to final destination in static/downloads ---
    if os.path.exists(temp_audio_file_path_with_ext) and final_audio_full_path:
        try:
            os.makedirs(os.path.dirname(final_audio_full_path), exist_ok=True)
            shutil.move(temp_audio_file_path_with_ext, final_audio_full_path) # shutil.move 更可靠
            logging.info(f"音频文件已保存为: {final_audio_full_path}")
            return relative_final_audio_path, True, f"下载并处理完成: {final_audio_filename_with_ext}"
        except OSError as e:
            msg = f"重命名/移动音频文件失败: {e}. 临时文件: {temp_audio_file_path_with_ext}, 目标: {final_audio_full_path}"
            logging.error(msg)
            # 如果移动失败，尝试清理临时文件
            if os.path.exists(temp_audio_file_path_with_ext): 
                try: os.remove(temp_audio_file_path_with_ext) 
                except OSError: pass
            return None, False, msg 
    elif os.path.exists(temp_audio_file_path_with_ext):
        msg = f"音频下载完成但无法确定最终文件名或路径。临时文件: {temp_audio_file_path_with_ext}"
        logging.error(msg)
        # 清理未移动的临时文件
        try: os.remove(temp_audio_file_path_with_ext) 
        except OSError: pass
        return None, False, msg
    else:
        # This case implies audio download failed earlier and was handled, 
        # but as a safeguard if logic reaches here without a temp file.
        logging.info("下载流程结束，但未找到临时音频文件进行最终移动。")
        return None, False, "音频下载失败或临时文件丢失"

# 移除之前的占位符注释 