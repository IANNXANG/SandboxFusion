import openai
import re
import os
import requests
import json
import base64

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
                    if len(content) > 100:  # 如果内容过长
                        # 显示前50个字符 + 省略标记 + 后50个字符
                        display_files[filename] = content[:50] + "...[省略 " + str(len(content) - 100) + " 个字符]..." + content[-50:]
                    else:
                        display_files[filename] = content
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
                
                success_info = {
                    'status': 'success',
                    'local_filename': local_filename,
                    'image_size': len(image_data),
                    'execution_result': result
                }
                
                print(f"\n✅ 图片已成功从沙盒获取并保存为: {local_filename}")
                print(f"图片大小: {len(image_data)} 字节")
                
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
    api_key="dummy-key"  # vllm通常不需要真实的API key
)

# 设置思考模式参数
#enable_thinking = True
enable_thinking = False

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

# 构建prompt
full_prompt = """
请生成一段Python代码，使用matplotlib库创建一个正弦曲线并保存为PNG文件。

要求：
1. 代码需要放在<code>和</code>标签中
2. 保存的PNG文件名需要放在<png>和</png>标签中
3. 代码应该是完整可执行的
4. 图片上所有文字都应该是英文

示例格式：
<code>
import matplotlib.pyplot as plt
# 你的绘图代码
plt.savefig('filename.png')
</code>
<png>filename.png</png>
"""


# 调用模型
response = client.chat.completions.create(
    model="8001vllm",
    messages=[
        {"role": "user", "content": full_prompt}
    ],
    max_tokens=2000,
    temperature=temperature,
    top_p=top_p,
    extra_body={
        "top_k": top_k,
        "min_p": min_p,
        "chat_template_kwargs": {"enable_thinking": enable_thinking}
    }
)

# 获取模型响应
model_response = response.choices[0].message.content
print("模型响应:")
print(model_response)
print("\n" + "="*50 + "\n")

# 提取代码部分 - 只匹配最后出现的<code></code>
code_pattern = r'<code>(.*?)</code>'
code_matches = re.findall(code_pattern, model_response, re.DOTALL)
if code_matches:
    code_matches = [code_matches[-1]]  # 只保留最后一个匹配

# 提取PNG文件名 - 只匹配最后出现的<png></png>
png_pattern = r'<png>(.*?)</png>'
png_matches = re.findall(png_pattern, model_response, re.DOTALL)
if png_matches:
    png_matches = [png_matches[-1]]  # 只保留最后一个匹配

if code_matches and png_matches:
    code = code_matches[0].strip()
    png_filename = png_matches[0].strip()
    
    print(f"提取到的代码:")
    print(code)
    print(f"\n提取到的PNG文件名: {png_filename}")
    
    # 使用封装的函数执行代码
    success, local_filename, result_info = run_code_in_sandbox(code, png_filename)
    
    if success:
        print(f"\n🎉 任务完成！生成的图片已保存为: {local_filename}")
    else:
        print(f"\n❌ 任务失败，详细信息: {result_info['status']}")
        if 'message' in result_info:
            print(f"错误信息: {result_info['message']}")
        if 'error' in result_info:
            print(f"异常信息: {result_info['error']}")
else:
    print("未能从模型响应中提取到完整的代码和文件名")
    if not code_matches:
        print("- 未找到<code>标签")
    if not png_matches:
        print("- 未找到<png>标签")
        