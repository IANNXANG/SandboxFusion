// 全局变量
let currentSessionId = null;
let statusCheckInterval = null;
let isGenerating = false;

// 状态更新函数
function updateStatus(status) {
    const statusElement = document.getElementById('status');
    const generateBtn = document.getElementById('generateBtn');
    
    statusElement.className = 'status ' + status;
    
    switch(status) {
        case 'idle':
            statusElement.textContent = '🟢 就绪';
            generateBtn.disabled = false;
            generateBtn.textContent = '开始生成';
            isGenerating = false;
            break;
        case 'running':
            statusElement.textContent = '🟡 生成中...';
            generateBtn.disabled = true;
            generateBtn.textContent = '生成中...';
            isGenerating = true;
            break;
        case 'completed':
            statusElement.textContent = '🟢 生成完成';
            generateBtn.disabled = false;
            generateBtn.textContent = '开始生成';
            isGenerating = false;
            break;
        case 'error':
            statusElement.textContent = '🔴 生成失败';
            generateBtn.disabled = false;
            generateBtn.textContent = '重新生成';
            isGenerating = false;
            break;
    }
}

// 标签页切换函数
function showTab(tabName) {
    // 隐藏所有标签页内容
    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(content => {
        content.classList.remove('active');
    });
    
    // 移除所有标签页的激活状态
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.classList.remove('active');
    });
    
    // 显示选中的标签页内容
    document.getElementById(tabName + 'Content').classList.add('active');
    
    // 激活选中的标签页
    event.target.classList.add('active');
}

// 添加日志条目函数
function addLogEntry(entry, index) {
    const container = document.getElementById('logsContainer');
    
    // 检查是否已存在该索引的日志条目
    let logDiv = container.children[index];
    
    if (!logDiv) {
        // 创建新的日志条目
        logDiv = document.createElement('div');
        logDiv.className = 'log-entry';
        
        if (entry.type === 'stream') {
            // 流式内容不显示时间戳，直接显示内容
            const message = document.createElement('span');
            message.className = 'log-' + entry.type;
            message.textContent = entry.message;
            logDiv.appendChild(message);
        } else {
            // 非流式内容显示时间戳
            const timestamp = document.createElement('span');
            timestamp.className = 'log-timestamp';
            timestamp.textContent = `[${entry.timestamp}] `;
            
            const message = document.createElement('span');
            message.className = 'log-' + entry.type;
            message.textContent = entry.message;
            
            logDiv.appendChild(timestamp);
            logDiv.appendChild(message);
        }
        
        container.appendChild(logDiv);
    } else if (entry.type === 'stream') {
        // 更新现有的流式日志条目
        const messageSpan = logDiv.querySelector('.log-stream');
        if (messageSpan) {
            messageSpan.textContent = entry.message;
        }
    }
    
    // 自动滚动到底部
    container.scrollTop = container.scrollHeight;
}

// 更新图片显示函数
function updateImages(images) {
    const container = document.getElementById('imagesContainer');
    
    if (images.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #666; padding: 40px;">暂无生成的图片</p>';
        return;
    }
    
    container.innerHTML = '';
    images.forEach(image => {
        const imageDiv = document.createElement('div');
        imageDiv.className = 'image-item';
        
        const img = document.createElement('img');
        img.src = '/images/' + image.filename.split('/').pop();
        img.alt = image.original_name;
        
        const info = document.createElement('div');
        info.className = 'image-info';
        info.innerHTML = `
            <strong>文件名:</strong> ${image.original_name}<br>
            <strong>生成时间:</strong> ${image.timestamp}
        `;
        
        imageDiv.appendChild(img);
        imageDiv.appendChild(info);
        container.appendChild(imageDiv);
    });
}

// 更新消息历史函数
function updateMessages(messages) {
    const container = document.getElementById('messagesContainer');
    
    if (messages.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #666; padding: 40px;">暂无对话历史</p>';
        return;
    }
    
    container.innerHTML = '';
    messages.forEach((message, index) => {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message-item';
        
        const role = document.createElement('div');
        role.className = 'message-role';
        role.textContent = `${message.role} (消息 ${index + 1})`;
        
        const content = document.createElement('div');
        content.className = 'message-content';
        content.textContent = message.content;
        
        messageDiv.appendChild(role);
        messageDiv.appendChild(content);
        container.appendChild(messageDiv);
    });
}

// 检查状态函数
function checkStatus() {
    if (!currentSessionId) return;
    
    fetch(`/status/${currentSessionId}`)
        .then(response => response.json())
        .then(data => {
            updateStatus(data.status);
            
            // 更新日志
            const container = document.getElementById('logsContainer');
            
            // 更新所有日志条目（包括流式更新）
            for (let i = 0; i < data.logs.length; i++) {
                addLogEntry(data.logs[i], i);
            }
            
            // 更新图片
            updateImages(data.images);
            
            // 如果生成完成，获取对话历史
            if (data.status === 'completed' || data.status === 'error') {
                fetch(`/messages/${currentSessionId}`)
                    .then(response => response.json())
                    .then(messageData => {
                        updateMessages(messageData.messages);
                    });
                
                // 停止状态检查
                if (statusCheckInterval) {
                    clearInterval(statusCheckInterval);
                    statusCheckInterval = null;
                }
            }
        })
        .catch(error => {
            console.error('状态检查失败:', error);
            updateStatus('error');
            if (statusCheckInterval) {
                clearInterval(statusCheckInterval);
                statusCheckInterval = null;
            }
        });
}

// 开始生成函数
function startGeneration() {
    if (isGenerating) return;
    
    const userPrompt = document.getElementById('userPrompt').value.trim();
    const enableThinking = document.getElementById('enableThinking').checked;
    
    if (!userPrompt) {
        alert('请输入用户提示词');
        return;
    }
    
    // 清空之前的内容
    document.getElementById('logsContainer').innerHTML = '';
    document.getElementById('imagesContainer').innerHTML = '<p style="text-align: center; color: #666; padding: 40px;">生成中...</p>';
    document.getElementById('messagesContainer').innerHTML = '<p style="text-align: center; color: #666; padding: 40px;">生成中...</p>';
    
    updateStatus('running');
    
    fetch('/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            user_prompt: userPrompt,
            enable_thinking: enableThinking
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert('生成失败: ' + data.error);
            updateStatus('error');
            return;
        }
        
        currentSessionId = data.session_id;
        
        // 开始定期检查状态
        statusCheckInterval = setInterval(checkStatus, 200);
    })
    .catch(error => {
        console.error('生成请求失败:', error);
        alert('生成请求失败: ' + error.message);
        updateStatus('error');
    });
}

// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', function() {
    updateStatus('idle');
    
    // 默认不启用思考模式
    document.getElementById('enableThinking').checked = false;
    
    // 绑定生成按钮事件
    document.getElementById('generateBtn').addEventListener('click', startGeneration);
    
    // 默认显示日志标签页
    document.querySelector('.tab').click();
});