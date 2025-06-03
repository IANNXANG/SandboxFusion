import openai
import re
import os
import requests
import json
import base64


# 设置思考模式参数
enable_thinking = False
#enable_thinking = True

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
            
            # 打印完整的沙盒执行结果（省略过长的base64字符串）
            print("\n=== 沙盒完整执行结果 ===")
            
            # 创建结果副本用于显示，省略过长的base64字符串
            display_result = result.copy()
            if 'files' in display_result:
                display_files = {}
                for filename, content in display_result['files'].items():
                        display_files[filename] = "base64 str"
                display_result['files'] = display_files
            
            print(json.dumps(display_result, indent=2, ensure_ascii=False))
            print("=" * 30)
            
            # 检查是否成功获取到文件
            if 'files' in result and png_filename in result['files']:
                # 解码base64图片数据
                image_data = base64.b64decode(result['files'][png_filename])
                
                # 保存图片到本地
                local_filename = f"downloaded_{png_filename}"
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
                
                print(f"\n✅ 图片已成功从沙盒获取并保存为: {local_filename}")
                
                return True, local_filename, success_info
            else:
                error_info = {
                    'status': 'file_not_found',
                    'message': '未能从沙盒获取到图片文件',
                    'execution_result': result
                }
                
                print("❌ 未能从沙盒获取到图片文件")
                if 'run_result' in result:
                    print("执行结果:", result['run_result'])
                
                return False, None, error_info
        else:
            error_info = {
                'status': 'api_error',
                'status_code': sandbox_response.status_code,
                'response_text': sandbox_response.text
            }
            
            print(f"❌ 沙盒API请求失败，状态码: {sandbox_response.status_code}")
            print("响应内容:", sandbox_response.text)
            
            return False, None, error_info
            
    except Exception as e:
        error_info = {
            'status': 'exception',
            'error': str(e)
        }
        
        print(f"\n调用沙盒API时出错: {e}")
        return False, None, error_info

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
else:
    # 非思考模式参数
    temperature = 0.7
    top_p = 0.8
    top_k = 20
    min_p = 0.0

# 构建system和user prompt
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

user_prompt = "使用matplotlib库创建一个正弦曲线并保存为PNG文件"


def stream_generate_with_tool_calling():
    """
    流式生成，当检测到</png>时停止生成并执行沙盒代码，然后继续生成
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    accumulated_response = ""
    png_detected = False
    
    while True:
        print(f"\n=== 开始生成（当前消息数: {len(messages)}）===")
        
        # 流式调用模型
        stream = client.chat.completions.create(
            model="8001vllm",
            messages=messages,
            max_tokens=2000,
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
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                current_chunk += content
                accumulated_response += content
                
                # 实时打印生成的内容
                print(content, end='', flush=True)
                
                # 检测是否出现了</png>
                if '</png>' in current_chunk:
                    png_detected = True
                    print("\n\n🔍 检测到</png>标签，停止生成...")
                    break
        
        print("\n" + "="*50)
        
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
                
                print(f"\n📝 提取到的代码:")
                print(code)
                print(f"\n🖼️ 提取到的PNG文件名: {png_filename}")
                
                # 执行沙盒代码
                success, local_filename, result_info = run_code_in_sandbox(code, png_filename)
                
                # 直接使用函数返回的display_result作为工具返回值
                if success:
                    tool_result = json.dumps(result_info['display_result'], indent=2, ensure_ascii=False)
                else:
                    tool_result = json.dumps(result_info, indent=2, ensure_ascii=False)
                
                # 将助手的响应和工具调用结果添加到消息历史
                messages.append({"role": "assistant", "content": accumulated_response})
                messages.append({
                    "role": "user", 
                    "content": f"""[工具执行结果]
{tool_result}

请根据执行结果继续回复。如果执行成功，请总结任务完成情况；如果执行失败，请分析原因并提供解决方案。"""
                })
                
                # 重置状态，准备继续生成
                accumulated_response = ""
                png_detected = False
                
                print(f"\n🔄 工具执行完成，继续生成...")
                continue
            else:
                print("\n❌ 未能从响应中提取到完整的代码和文件名")
                break
        else:
            # 如果没有检测到</png>，说明生成完成
            print("\n✅ 生成完成，未检测到新的</png>标签")
            break
    
    return accumulated_response, messages

# 执行流式生成
final_response, messages = stream_generate_with_tool_calling()
print("\n🎯 最终响应:")
print(final_response)

# 打印完整的消息历史
print("\n" + "="*60)
print("📋 完整消息历史:")
print("="*60)
for i, message in enumerate(messages):
    print(f"消息 {i+1}: {message}")
print("="*60)