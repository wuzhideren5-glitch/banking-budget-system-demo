import { useState } from "react";
import { Send, MessageSquare, Sparkles, Upload, Mic, Phone, Plus, History, Maximize2, Minimize2 } from "lucide-react";

interface Message {
  id: string;
  type: "user" | "bot";
  content: string;
  time: string;
}

export function ChatBot() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      type: "bot",
      content: "您好！我是预算智能助手，有什么可以帮您的吗？",
      time: "14:30",
    },
  ]);
  const [input, setInput] = useState("");
  const [isExpanded, setIsExpanded] = useState(false);

  const handleSend = () => {
    if (!input.trim()) return;

    const newMessage: Message = {
      id: Date.now().toString(),
      type: "user",
      content: input,
      time: new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages([...messages, newMessage]);
    setInput("");

    // 模拟机器人回复
    setTimeout(() => {
      const botReply: Message = {
        id: (Date.now() + 1).toString(),
        type: "bot",
        content: "我正在分析您的问题，请稍候...",
        time: new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, botReply]);
    }, 500);
  };

  return (
    <div className="h-full bg-[#f5f6fa] border-l border-gray-300 flex flex-col">
      <div className="h-10 bg-white border-b border-gray-300 flex items-center justify-between px-3">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-gray-600" />
          <span className="text-xs font-medium text-gray-700">智能助手</span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            className="flex items-center gap-1 px-2 py-1 text-xs bg-[#3498db] text-white hover:bg-[#2980b9] rounded transition-colors"
            title="新对话"
          >
            <Plus className="w-3 h-3" />
            <span>新对话</span>
          </button>
          <button
            className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 text-gray-700 hover:bg-gray-200 rounded transition-colors"
            title="历史对话"
          >
            <History className="w-3 h-3" />
            <span>历史</span>
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.type === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded px-2.5 py-1.5 ${
                msg.type === "user"
                  ? "bg-[#3498db] text-white"
                  : "bg-white border border-gray-200 text-gray-700"
              }`}
            >
              <p className="text-xs leading-relaxed">{msg.content}</p>
              <p
                className={`text-[10px] mt-1 ${
                  msg.type === "user" ? "text-blue-100" : "text-gray-400"
                }`}
              >
                {msg.time}
              </p>
            </div>
          </div>
        ))}
      </div>

      <div className="p-3 bg-white border-t border-gray-300">
        <div className="flex gap-2 mb-2">
          {isExpanded ? (
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="输入您的问题... (Shift+Enter换行，Enter发送)"
              className="flex-1 px-2.5 py-1.5 text-xs border border-gray-300 rounded focus:outline-none focus:border-[#3498db] bg-white resize-none overflow-y-auto"
              style={{ height: "120px" }}
            />
          ) : (
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && handleSend()}
              placeholder="输入您的问题..."
              className="flex-1 px-2.5 py-1.5 text-xs border border-gray-300 rounded focus:outline-none focus:border-[#3498db] bg-white"
            />
          )}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="px-2 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded transition-colors"
            title={isExpanded ? "收起输入框" : "展开输入框"}
          >
            {isExpanded ? (
              <Minimize2 className="w-3.5 h-3.5" />
            ) : (
              <Maximize2 className="w-3.5 h-3.5" />
            )}
          </button>
          <button
            onClick={handleSend}
            className="px-3 py-1.5 bg-[#3498db] text-white rounded hover:bg-[#2980b9] transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="flex gap-1.5 justify-center">
          <button
            className="p-2 bg-gray-100 hover:bg-gray-200 rounded transition-colors text-gray-700"
            title="智能提问"
          >
            <Sparkles className="w-4 h-4" />
          </button>
          <button
            className="p-2 bg-gray-100 hover:bg-gray-200 rounded transition-colors text-gray-700"
            title="上传文件"
          >
            <Upload className="w-4 h-4" />
          </button>
          <button
            className="p-2 bg-gray-100 hover:bg-gray-200 rounded transition-colors text-gray-700"
            title="语音输入"
          >
            <Mic className="w-4 h-4" />
          </button>
          <button
            className="p-2 bg-gray-100 hover:bg-gray-200 rounded transition-colors text-gray-700"
            title="电话交流"
          >
            <Phone className="w-4 h-4" />
          </button>
          <button
            className="p-2 bg-gray-100 hover:bg-gray-200 rounded transition-colors text-gray-700"
            title="历史问题"
          >
            <History className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
