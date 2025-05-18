import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify, session
import music_api_handler # 我们的核心逻辑模块
import logging
from datetime import datetime
import database # 导入我们的数据库模块
from functools import wraps # 导入 wraps
import time # 新增导入

app = Flask(__name__)
app.secret_key = os.urandom(24) # 用于 flash messages 和 session

# 播放历史记录最大保存数量
MAX_HISTORY_ITEMS = 10
# 最近搜索记录最大保存数量
MAX_RECENT_SEARCHES = 8
# 旧文件最大保留天数
MAX_FILE_AGE_DAYS = 7 # 新增常量

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app.logger.setLevel(logging.INFO)

# 获取应用的 static 文件夹的绝对路径
# Flask 会自动在 templates 同级目录寻找 static 文件夹
APP_STATIC_FOLDER = os.path.join(app.root_path, 'static')
DOWNLOAD_PATH = os.path.join(APP_STATIC_FOLDER, music_api_handler.DOWNLOAD_DIR_NAME)
TEMP_PATH = os.path.join(APP_STATIC_FOLDER, music_api_handler.TEMP_DIR_NAME)

# 确保下载和临时目录存在
os.makedirs(DOWNLOAD_PATH, exist_ok=True)
os.makedirs(TEMP_PATH, exist_ok=True)

# --- 上下文处理器，注入全局变量到模板 ---
@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now().year}

# --- 文件清理函数 ---
def cleanup_old_files(folder_path, max_age_days):
    """清理指定文件夹中超过指定天数的旧文件"""
    if not os.path.isdir(folder_path):
        app.logger.warning(f"清理目录不存在: {folder_path}")
        return
    
    app.logger.info(f"开始清理目录: {folder_path}, 清理 {max_age_days} 天前的旧文件")
    count_deleted = 0
    count_failed = 0
    max_age_seconds = max_age_days * 24 * 60 * 60
    current_time = time.time()

    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                file_mod_time = os.path.getmtime(file_path)
                if (current_time - file_mod_time) > max_age_seconds:
                    os.remove(file_path)
                    app.logger.info(f"已删除旧文件: {file_path}")
                    count_deleted += 1
            # 注意: 如果需要递归清理子目录，需要添加 os.walk
        except Exception as e:
            app.logger.error(f"删除文件 {file_path} 失败: {e}")
            count_failed += 1
    app.logger.info(f"目录 {folder_path} 清理完成。删除了 {count_deleted} 个文件, 失败 {count_failed} 个。")

# 初始化数据库 和 清理旧文件 (在应用启动时直接调用)
with app.app_context():
    database.init_db()
    app.logger.info("Database initialized directly on app setup.")
    
    # 应用启动时清理旧文件
    cleanup_old_files(DOWNLOAD_PATH, MAX_FILE_AGE_DAYS)
    cleanup_old_files(TEMP_PATH, MAX_FILE_AGE_DAYS)

# --- User Authentication Helper ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录以访问此页面。', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', search_performed=False)

@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('query')
    if not query or not query.strip():
        flash('请输入搜索关键词！', 'warning')
        return redirect(url_for('index'))
    
    # 保存到最近搜索记录
    if 'recent_searches' not in session:
        session['recent_searches'] = []
    
    recent_searches = session['recent_searches']
    
    # 如果已存在相同查询，先移除
    if query in recent_searches:
        recent_searches.remove(query)
    
    # 添加到列表开头
    recent_searches.insert(0, query)
    
    # 限制数量
    if len(recent_searches) > MAX_RECENT_SEARCHES:
        recent_searches = recent_searches[:MAX_RECENT_SEARCHES]
    
    session['recent_searches'] = recent_searches
    session.modified = True
    
    app.logger.info(f"收到搜索请求: {query}")
    songs = music_api_handler.search_music(query)
    
    if songs:
        flash(f"找到 {len(songs)} 首相关歌曲。", 'success')
    else:
        flash('未找到相关歌曲，请尝试其他关键词。', 'info')
    return render_template('index.html', songs=songs, query=query, search_performed=True)

@app.route('/song/<path:query>/<song_api_index>')
def song_player(query, song_api_index):
    app.logger.info(f"请求播放歌曲: query={query}, api_index={song_api_index}")
    
    # 检查播放来源
    source = request.args.get('source', 'search')  # 默认来源为搜索
    playlist_id = request.args.get('playlist_id')
    
    song_details = music_api_handler.get_song_details(query, song_api_index)

    if not song_details or not song_details.get('url'):
        flash('无法获取歌曲详情或播放链接，请重试。', 'error')
        return redirect(request.referrer or url_for('index'))

    # 获取播放列表（根据来源不同而不同）
    playlist = None
    playlist_songs = []
    search_results = []
    
    if source == 'playlist' and playlist_id:
        # 从歌单播放
        try:
            playlist_id = int(playlist_id)
            if 'user_id' in session:  # 用户已登录
                playlist = database.get_playlist_by_id(playlist_id, session.get('user_id'))
            
            if playlist:
                playlist_songs = database.get_songs_in_playlist(playlist_id)
                app.logger.info(f"从歌单播放，获取到 {len(playlist_songs)} 首歌曲")
            else:
                # 如果未找到歌单或无权访问，回退到搜索结果
                app.logger.warning(f"歌单 ID {playlist_id} 未找到或无权访问，回退到搜索结果")
                source = 'search'
        except (ValueError, TypeError) as e:
            app.logger.error(f"处理歌单 ID 时出错: {e}")
            source = 'search'
    
    # 如果来源是搜索或无法获取歌单，则获取搜索结果
    if source == 'search' or not playlist_songs:
        try:
            search_results = music_api_handler.search_music(query) or []
            app.logger.info(f"从搜索结果播放，获取到 {len(search_results)} 首歌曲")
        except Exception as e:
            app.logger.warning(f"获取搜索结果列表失败: {e}")

    # 确定上一首和下一首歌曲
    prev_song_nav = None
    next_song_nav = None
    current_song_list_index = -1
    
    # 根据来源使用不同的列表查找当前歌曲位置
    song_list = playlist_songs if source == 'playlist' and playlist_songs else search_results
 
    if song_list:
        try:
            current_url_song_api_index_str = str(song_api_index)

            for i, song in enumerate(song_list):
                if source == 'playlist':
                    # sqlite3.Row objects are accessed by index/key
                    song_item_api_index_original = song['song_api_index'] 
                else:
                    # search_results are expected to be dicts and support .get()
                    song_item_api_index_original = song.get('index')
                
                song_item_api_index_str = str(song_item_api_index_original)
                

                if song_item_api_index_str == current_url_song_api_index_str:
                    current_song_list_index = i

                    break
            
            if current_song_list_index == -1:
                app.logger.warning("[DEBUG] song_player - No match found for current song in the list!")

            if current_song_list_index != -1:
                if current_song_list_index > 0:
                    prev_song = song_list[current_song_list_index - 1]
                    if source == 'playlist':
                        prev_song_nav = {
                            'query': prev_song['song_query'], 
                            'song_api_index': prev_song['song_api_index'],
                            'source': source,
                            'playlist_id': playlist_id
                        }
                    else: # source == 'search'
                        prev_song_nav = {
                            'query': query, 
                            'song_api_index': prev_song.get('index'),
                            'source': source,
                            'playlist_id': None
                        }
                
                if current_song_list_index < len(song_list) - 1:
                    next_song = song_list[current_song_list_index + 1]
                    if source == 'playlist':
                        next_song_nav = {
                            'query': next_song['song_query'], 
                            'song_api_index': next_song['song_api_index'],
                            'source': source,
                            'playlist_id': playlist_id
                        }
                    else: # source == 'search'
                        next_song_nav = {
                            'query': query, 
                            'song_api_index': next_song.get('index'),
                            'source': source,
                            'playlist_id': None
                        }
        except Exception as e:
            app.logger.error(f"确定上一首/下一首歌曲时出错: {e}")

    # 添加到播放历史记录
    if song_details and 'url' in song_details:
        # 初始化session中的历史记录（如果不存在）
        if 'play_history' not in session:
            session['play_history'] = []
        
        # 创建历史记录项
        history_item = {
            'id': song_api_index,  # 用于唯一标识歌曲
            'title': song_details.get('title', '未知歌曲'),
            'singer': song_details.get('singer', '未知歌手'),
            'cover': song_details.get('cover', ''),
            'query': query,
            'played_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 检查是否已存在相同歌曲
        play_history = session['play_history']
        play_history = [item for item in play_history if item.get('id') != song_api_index]
        
        # 将新历史记录添加到列表开头
        play_history.insert(0, history_item)
        
        # 限制历史记录数量
        if len(play_history) > MAX_HISTORY_ITEMS:
            play_history = play_history[:MAX_HISTORY_ITEMS]
            
        session['play_history'] = play_history
        session.modified = True

    user_playlists = []
    if 'user_id' in session:
        user_playlists = database.get_playlists_by_user_id(session['user_id'])

    parsed_lyrics = []
    if song_details.get('lyric'):
        lines = song_details['lyric'].strip().split('\n')
        for line in lines:
            parsed_line = music_api_handler.parse_lrc_line(line)
            if parsed_line:
                parsed_lyrics.append({'time_ms': parsed_line[0], 'text': parsed_line[1]})
            # else:
                # If you want to include lines without timestamps, handle them here.
                # For example, add them with a time_ms of 0 or a special flag.
                # parsed_lyrics.append({'time_ms': 0, 'text': line}) # Example

    # 如果API返回的歌曲URL是相对路径或需要特殊处理，在这里调整
    # song_details['url'] = make_url_absolute_if_needed(song_details['url'])

    app.logger.info(f"歌曲详情: {song_details.get('title')}, 播放链接: {song_details.get('url')}")
    if parsed_lyrics:
        app.logger.info(f"解析到 {len(parsed_lyrics)} 行带时间戳的歌词。")
    else:
        app.logger.info("未解析到带时间戳的歌词，将显示原始歌词文本。")
        
    return render_template(
        'song_player.html',
        song_details=song_details,
        parsed_lyrics=parsed_lyrics,
        original_query=query, 
        song_api_index=song_api_index, 
        search_results=search_results, 
        user_playlists=user_playlists,
        prev_song_nav=prev_song_nav,
        next_song_nav=next_song_nav,
        source=source,
        playlist=playlist,
        playlist_songs=playlist_songs if source == 'playlist' else None,
        playlist_id=playlist_id if source == 'playlist' else None
    )

@app.route('/download/<path:query>/<song_api_index>')
def download_song(query, song_api_index):
    app.logger.info(f"请求下载歌曲: query={query}, api_index={song_api_index}")
    song_details = music_api_handler.get_song_details(query, song_api_index)

    if not song_details:
        flash('无法获取歌曲详情以下载。', 'error')
        return redirect(request.referrer or url_for('index'))

    # APP_STATIC_FOLDER 是我们之前定义的 static 文件夹的绝对路径
    relative_audio_path, success, message = music_api_handler.download_song_assets_for_web(
        song_details,
        APP_STATIC_FOLDER
    )

    if success:
        if relative_audio_path and "文件已存在" not in message:
            flash(f"歌曲 '{song_details.get('title', '未知歌曲')}' 下载处理完成: {message}", 'success')
        elif relative_audio_path and "文件已存在" in message:
            flash(f"歌曲 '{song_details.get('title', '未知歌曲')}' 已存在，可直接下载。", 'info')
        else: # Should not happen if success is True and relative_audio_path is None
            flash(f"歌曲 '{song_details.get('title', '未知歌曲')}' 处理完成，但未获取到文件路径。", 'warning')
            return redirect(request.referrer or url_for('index'))
        
        # relative_audio_path 类似 'downloads/filename.mp3'
        # send_from_directory 需要目录和文件名分开
        directory = os.path.join(APP_STATIC_FOLDER, os.path.dirname(relative_audio_path))
        filename = os.path.basename(relative_audio_path)
        app.logger.info(f"尝试发送文件: 目录='{directory}', 文件名='{filename}'")
        try:
            return send_from_directory(directory, filename, as_attachment=True)
        except Exception as e:
            app.logger.error(f"发送文件时出错: {e}")
            flash(f"下载 '{filename}' 失败: 无法从服务器发送文件。", 'error')
            return redirect(request.referrer or url_for('index'))
            
    else:
        flash(f"下载歌曲 '{song_details.get('title', '未知歌曲')}' 失败: {message}", 'error')
        return redirect(request.referrer or url_for('index'))

@app.route('/history')
def play_history():
    """显示用户的播放历史"""
    history = session.get('play_history', [])
    return render_template('history.html', history=history)

@app.route('/clear_history')
def clear_history():
    """清空播放历史"""
    if 'play_history' in session:
        session.pop('play_history')
        flash('播放历史已清空', 'success')
    return redirect(url_for('play_history'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index')) # 如果已登录，重定向到首页
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if not username or len(username) < 3 or len(username) > 30:
            flash('用户名长度必须在3到30个字符之间。', 'error')
            return render_template('login.html')

        user = database.get_user_by_username(username)
        if not user:
            user = database.create_user(username)
            if user:
                flash(f'欢迎你，新朋友 {user["username"]}！你的账户已创建。', 'success')
            else:
                flash('创建账户时发生错误，请稍后再试。', 'error')
                return render_template('login.html')
        else:
            flash(f'欢迎回来，{user["username"]}！', 'success')
        
        if user: # 确保用户对象存在
            session['user_id'] = user['id']
            session['username'] = user['username']
            app.logger.info(f"User {user['username']} (ID: {user['id']}) logged in.")
            
            next_url = request.args.get('next')
            return redirect(next_url or url_for('index'))
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    username = session.get('username', '用户')
    session.pop('user_id', None)
    session.pop('username', None)
    # 清空其他 session 数据，例如播放历史和最近搜索，因为它们是用户相关的
    session.pop('play_history', None)
    session.pop('recent_searches', None)
    flash(f'{username}，你已成功登出。', 'info')
    app.logger.info(f"User {username} logged out.")
    return redirect(url_for('index'))

@app.route('/my_playlists')
@login_required
def my_playlists():
    user_id = session['user_id']
    playlists = database.get_playlists_by_user_id(user_id)
    return render_template('my_playlists.html', playlists=playlists)

@app.route('/playlist/create', methods=['POST'])
@login_required
def create_playlist_route(): # Renamed to avoid conflict with database.create_playlist
    user_id = session['user_id']
    playlist_name = request.form.get('playlist_name', '').strip()
    if not playlist_name or len(playlist_name) > 50:
        flash('歌单名称不能为空且不能超过50个字符。', 'error')
    else:
        playlist_id = database.create_playlist(user_id, playlist_name)
        if playlist_id:
            flash(f"歌单 '{playlist_name}' 创建成功！", 'success')
            return redirect(url_for('playlist_detail', playlist_id=playlist_id))
        else:
            flash('创建歌单失败，请稍后再试。', 'error')
    return redirect(url_for('my_playlists'))

@app.route('/playlist/<int:playlist_id>')
@login_required
def playlist_detail(playlist_id):
    user_id = session['user_id']
    playlist = database.get_playlist_by_id(playlist_id, user_id)
    if not playlist:
        flash('未找到该歌单或无权访问。', 'error')
        return redirect(url_for('my_playlists'))
    
    # 获取歌单中的歌曲 (后续实现)
    songs_in_playlist = database.get_songs_in_playlist(playlist_id)
    
    return render_template('playlist_detail.html', playlist=playlist, songs=songs_in_playlist)

@app.route('/playlist/delete/<int:playlist_id>', methods=['POST'])
@login_required
def delete_playlist(playlist_id):
    user_id = session['user_id']
    deleted = database.delete_playlist_by_id(playlist_id, user_id)
    if deleted:
        flash('歌单已成功删除。', 'success')
    else:
        flash('删除歌单失败或无权操作。', 'error')
    return redirect(url_for('my_playlists'))

@app.route('/playlist/<int:playlist_id>/add_song', methods=['POST'])
@login_required
def add_song_to_playlist_route(playlist_id):
    if 'user_id' not in session:
        flash('请先登录!', 'warning')
        return redirect(url_for('login'))

    playlist = database.get_playlist_by_id(playlist_id)
    if not playlist or playlist['user_id'] != session['user_id']:
        flash('歌单不存在或无权操作。', 'error')
        return redirect(url_for('my_playlists'))

    song_api_index = request.form.get('song_api_index')
    song_query = request.form.get('original_query') # 在 song_player.html 中确保这个字段名正确
    title = request.form.get('title')
    singer = request.form.get('singer')
    cover = request.form.get('cover')

    if not all([song_api_index, song_query, title, singer]):
        flash('歌曲信息不完整，无法添加到歌单。', 'error')
        # 如果这些信息确实来自表单，那么重定向回播放器页面可能更合适
        # 但需要确保 song_player 页面能正确处理缺少部分信息的情况，或者确保这些信息总是被传递
        if song_query and song_api_index:
            return redirect(url_for('song_player', query=song_query, song_api_index=song_api_index))
        return redirect(url_for('index'))


    success, message = database.add_song_to_playlist(
        playlist_id,
        song_api_index,
        song_query,
        title,
        singer,
        cover
    )

    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    # 用户要求：添加成功后，返回到歌曲播放页面，而不是歌单详情页
    # 确保 original_query 和 song_api_index 能从表单中正确获取
    original_query_for_redirect = request.form.get('original_query')
    song_api_index_for_redirect = request.form.get('song_api_index')

    if original_query_for_redirect and song_api_index_for_redirect:
        app.logger.info(f"Redirecting to song_player with query: {original_query_for_redirect}, index: {song_api_index_for_redirect}")
        return redirect(url_for('song_player', query=original_query_for_redirect, song_api_index=song_api_index_for_redirect))
    else:
        # 如果无法获取必要参数，则回退到首页或我的歌单页面
        app.logger.warning("Could not get original_query or song_api_index for redirect, falling back to my_playlists.")
        return redirect(url_for('my_playlists'))

@app.route('/playlist/<int:playlist_id>/remove_song/<int:song_id>', methods=['POST'])
@login_required
def remove_song_from_playlist(playlist_id, song_id):
    user_id = session['user_id']
    # 验证歌单是否属于当前用户 (通过 remove_song_from_playlist 内部的权限检查)
    # playlist = database.get_playlist_by_id(playlist_id, user_id)
    # if not playlist:
    #     flash('未找到歌单或无权操作。', 'error')
    #     return redirect(url_for('my_playlists'))

    removed = database.remove_song_from_playlist(song_id, user_id) # song_id is playlist_songs.id

    if removed:
        flash('歌曲已从歌单中移除。', 'success')
    else:
        flash('移除歌曲失败或无权操作。', 'error')
    
    return redirect(url_for('playlist_detail', playlist_id=playlist_id))

# 后续将添加更多路由
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001) 