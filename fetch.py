import json
import base64
import requests

# 创建matplotlib图片的代码
matplotlib_code = '''
import matplotlib.pyplot as plt
import numpy as np

# 创建示例数据
x = np.linspace(0, 10, 100)
y = np.sin(x)

# 创建图形
plt.figure(figsize=(10, 6))
plt.plot(x, y, 'b-', linewidth=2, label='sin(x)')
plt.title('Matplotlib示例图片', fontsize=16)
plt.xlabel('X轴', fontsize=12)
plt.ylabel('Y轴', fontsize=12)
plt.grid(True, alpha=0.3)
plt.legend()

# 保存图片到文件
plt.savefig('my_plot.png', dpi=300, bbox_inches='tight')
plt.close()  # 关闭图形以释放内存

print("图片已保存为 my_plot.png")
'''

# 发送请求到沙盒API
response = requests.post('http://localhost:8080/run_code', json={
    'code': matplotlib_code,
    'language': 'python',
    'fetch_files': ['my_plot.png']  # 指定要获取的图片文件
})

# 检查响应状态
if response.status_code == 200:
    result = response.json()
    
    # 打印完整响应（可选）
    print("API响应:")
    print(json.dumps(result, indent=2))
    
    # 检查是否成功获取到文件
    if 'files' in result and 'my_plot.png' in result['files']:
        # 解码base64图片数据
        image_data = base64.b64decode(result['files']['my_plot.png'])
        
        # 保存图片到本地
        with open('downloaded_plot.png', 'wb') as f:
            f.write(image_data)
        
        print("\n✅ 图片已成功从沙盒获取并保存为 'downloaded_plot.png'")
        print(f"图片大小: {len(image_data)} 字节")
    else:
        print("❌ 未能获取到图片文件")
        if 'run_result' in result:
            print("执行结果:", result['run_result'])
else:
    print(f"❌ API请求失败，状态码: {response.status_code}")
    print("响应内容:", response.text)