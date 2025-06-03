from flask import Flask, render_template, request, jsonify, send_file
import openai
import re
import os
import requests
import json
import base64
import threading
import time
from datetime import datetime
import uuid

app = Flask(__name__)

# 全局变量存储会话状态
sessions = {}

def run_code_in_sandbox(code, png_filename):
    """
    在沙盒中执行代码并下载生成的图片文件
    
    Args:
        code (str): 要执行的Python代码
        png_filename (str): 期望生成的PNG文件名
    
    Returns:
        tuple: (success, local_filename, result_info)
            success: 是否成功
            local_filename: 本地保存的文件名（如果成功）
            result_info: 详细的执行结果信息
    """
    try:
        print("\n正在通过沙盒执行生成的代码...")
        
        # 发送请求到沙盒API
        sandbox_response = requests.post('http://localhost:8080/run_code', json={
            'code': code,
            'language': 'python',
            'fetch_files': [png_filename]  # 指定要获取的图片文件
        })
        
        # 检查响应状态
        if sandbox_response.status_code == 200:
            result = sandbox_response.json()
            
            # 创建结果副本用于显示，省略过长的base64字符串
            display_result = result.copy()
            if 'files' in display_result:
                display_files = {}
                for filename, content in display_result['files'].items():
                    display_files[filename] = "base64 str"
                display_result['files'] = display_files
            
            # 检查是否成功获取到文件
            if 'files' in result and png_filename in result['files']:
                # 解码base64图片数据
                image_data = base64.b64decode(result['files'][png_filename])
                
                # 保存图片到本地
                local_filename = f"static/images/downloaded_{png_filename}"
                os.makedirs(os.path.dirname(local_filename), exist_ok=True)
                with open(local_filename, 'wb') as f:
                    f.write(image_data)
                
                # 添加本地文件信息到display_result
                display_result['local_filename'] = local_filename
                display_result['image_size'] = len(image_data)
                
                success_info = {
                    'status': 'success',
                    'local_filename': local_filename,
                    'image_size': len(image_data),
                    'execution_result': result,
                    'display_result': display_result
                }
                
                return True, local_filename, success_info
            else:
                error_info = {
                    'status': 'file_not_found',
                    'message': '未能从沙盒获取到图片文件',
                    'execution_result': result
                }
                
                return False, None, error_info
        else:
            error_info = {
                'status': 'api_error',
                'status_code': sandbox_response.status_code,
                'response_text': sandbox_response.text
            }
            
            return False, None, error_info
            
    except Exception as e:
        error_info = {
            'status': 'exception',
            'error': str(e)
        }
        
        return False, None, error_info

def stream_generate_with_tool_calling(user_prompt, enable_thinking, session_id):
    """
    流式生成，当检测到</png>时停止生成并执行沙盒代码，然后继续生成
    """
    # 配置OpenAI客户端连接到本地vllm服务
    client = openai.OpenAI(
        base_url="http://localhost:8001/v1",
        api_key="dummy-key" 
    )
    
    # 根据思考模式设置不同的参数
    if enable_thinking:
        # 思考模式参数
        temperature = 0.6
        top_p = 0.95
        top_k = 20
        min_p = 0.0
        max_token = 20480
    else:
        # 非思考模式参数
        temperature = 0.7
        top_p = 0.8
        top_k = 20
        min_p = 0.0
        max_token = 20480
    
    # 构建system prompt
    system_prompt = """
请生成一段Python代码。

要求：
1. 代码需要放在<code>和</code>标签中
2. 保存的PNG文件名需要放在<png>和</png>标签中
3. 代码应该是完整可执行的
4. 图片上所有文字都应该是英文
5. 绘图美观，这是一个学术报告的插图

示例格式：
<code>
import matplotlib.pyplot as plt
# 你的绘图代码
plt.savefig('filename.png')
</code>

<png>filename.png</png>
"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    accumulated_response = ""
    png_detected = False
    
    # 获取已初始化的会话状态
    session = sessions[session_id]
    
    while True:
        log_entry = {
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'type': 'info',
            'message': f"开始生成（当前消息数: {len(messages)}）"
        }
        session['logs'].append(log_entry)
        
        # 流式调用模型
        stream = client.chat.completions.create(
            model="8001vllm",
            messages=messages,
            max_tokens=max_token,
            temperature=temperature,
            top_p=top_p,
            stream=True,
            extra_body={
                "top_k": top_k,
                "min_p": min_p,
                "chat_template_kwargs": {"enable_thinking": enable_thinking}
            }
        )
        
        current_chunk = ""
        
        # 处理流式响应
        stream_buffer = ""
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                current_chunk += content
                accumulated_response += content
                stream_buffer += content
                
                # 更新流式内容到会话（累积显示）
                if len(session['logs']) > 0 and session['logs'][-1]['type'] == 'stream':
                    # 更新最后一个流式日志条目
                    session['logs'][-1]['message'] = stream_buffer
                else:
                    # 创建新的流式日志条目
                    session['logs'].append({
                        'timestamp': datetime.now().strftime('%H:%M:%S'),
                        'type': 'stream',
                        'message': stream_buffer
                    })
                
                # 检测是否出现了</png>
                if '</png>' in current_chunk:
                    png_detected = True
                    session['logs'].append({
                        'timestamp': datetime.now().strftime('%H:%M:%S'),
                        'type': 'info',
                        'message': "🔍 检测到</png>标签，停止生成..."
                    })
                    break
        
        # 如果检测到</png>，执行沙盒代码
        if png_detected:
            # 提取代码和文件名
            think_pattern = r'<think>.*?</think>'
            filtered_response = re.sub(think_pattern, '', accumulated_response, flags=re.DOTALL)
            
            code_pattern = r'<code>(.*?)</code>'
            code_matches = re.findall(code_pattern, filtered_response, re.DOTALL)
            
            png_pattern = r'<png>(.*?)</png>'
            png_matches = re.findall(png_pattern, filtered_response, re.DOTALL)
            
            if code_matches and png_matches:
                code = code_matches[-1].strip()  # 取最后一个匹配
                png_filename = png_matches[-1].strip()  # 取最后一个匹配
                
                session['logs'].append({
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'type': 'code',
                    'message': f"📝 提取到的代码:\n{code}"
                })
                
                session['logs'].append({
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'type': 'info',
                    'message': f"🖼️ 提取到的PNG文件名: {png_filename}"
                })
                
                # 执行沙盒代码
                success, local_filename, result_info = run_code_in_sandbox(code, png_filename)
                
                # 记录执行结果
                if success:
                    tool_result = json.dumps(result_info['display_result'], indent=2, ensure_ascii=False)
                    session['logs'].append({
                        'timestamp': datetime.now().strftime('%H:%M:%S'),
                        'type': 'success',
                        'message': f"✅ 图片已成功从沙盒获取并保存为: {local_filename}"
                    })
                    session['images'].append({
                        'filename': local_filename,
                        'original_name': png_filename,
                        'timestamp': datetime.now().strftime('%H:%M:%S')
                    })
                else:
                    tool_result = json.dumps(result_info, indent=2, ensure_ascii=False)
                    session['logs'].append({
                        'timestamp': datetime.now().strftime('%H:%M:%S'),
                        'type': 'error',
                        'message': "❌ 未能从沙盒获取到图片文件"
                    })
                
                session['logs'].append({
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'type': 'result',
                    'message': f"沙盒执行结果:\n{tool_result}"
                })
                
                # 将助手的响应添加到消息历史（过滤掉think标签内容）
                think_pattern = r'<think>.*?</think>'
                filtered_assistant_response = re.sub(think_pattern, '', accumulated_response, flags=re.DOTALL)
                messages.append({"role": "assistant", "content": filtered_assistant_response})
                messages.append({
                    "role": "tool", 
                    "content": f"""[工具执行结果]
{tool_result}

请根据执行结果继续回复。如果执行成功，请总结任务完成情况；如果执行失败，请分析原因并提供解决方案。"""
                })
                
                # 重置状态，准备继续生成
                accumulated_response = ""
                png_detected = False
                
                session['logs'].append({
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'type': 'info',
                    'message': "🔄 工具执行完成，继续生成..."
                })
                continue
            else:
                session['logs'].append({
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'type': 'error',
                    'message': "❌ 未能从响应中提取到完整的代码和文件名"
                })
                break
        else:
            # 如果没有检测到</png>，说明生成完成
            session['logs'].append({
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'type': 'info',
                'message': "✅ 生成完成，未检测到新的</png>标签"
            })
            break
    
    # 过滤最终响应中的think标签内容
    think_pattern = r'<think>.*?</think>'
    final_filtered_response = re.sub(think_pattern, '', accumulated_response, flags=re.DOTALL)
    
    # 将最终的助手响应添加到消息历史中
    if final_filtered_response.strip():  # 只有当响应不为空时才添加
        messages.append({"role": "assistant", "content": final_filtered_response})
    
    # 保存完整对话历史
    session['messages'] = messages
    session['status'] = 'completed'
    
    return messages

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    user_prompt = data.get('user_prompt', '')
    enable_thinking = data.get('enable_thinking', False)
    
    if not user_prompt.strip():
        return jsonify({'error': '用户提示不能为空'}), 400
    
    # 生成会话ID
    session_id = str(uuid.uuid4())
    
    # 立即初始化会话状态
    sessions[session_id] = {
        'logs': [],
        'messages': [],
        'images': [],
        'status': 'initializing'
    }
    
    # 在后台线程中执行生成
    def run_generation():
        try:
            # 更新状态为运行中
            sessions[session_id]['status'] = 'running'
            stream_generate_with_tool_calling(user_prompt, enable_thinking, session_id)
        except Exception as e:
            if session_id in sessions:
                sessions[session_id]['logs'].append({
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'type': 'error',
                    'message': f"生成过程中出错: {str(e)}"
                })
                sessions[session_id]['status'] = 'error'
    
    thread = threading.Thread(target=run_generation)
    thread.daemon = True
    thread.start()
    
    return jsonify({'session_id': session_id})

@app.route('/status/<session_id>')
def get_status(session_id):
    if session_id not in sessions:
        return jsonify({'error': '会话不存在'}), 404
    
    session = sessions[session_id]
    return jsonify({
        'status': session['status'],
        'logs': session['logs'],
        'images': session['images'],
        'message_count': len(session['messages'])
    })

@app.route('/messages/<session_id>')
def get_messages(session_id):
    if session_id not in sessions:
        return jsonify({'error': '会话不存在'}), 404
    
    session = sessions[session_id]
    return jsonify({
        'messages': session['messages']
    })

@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_file(f'static/images/{filename}')

if __name__ == '__main__':
    # 确保静态文件夹存在
    os.makedirs('static/images', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)