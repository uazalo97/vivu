/**
 * Vùng nhập liệu: textarea auto-grow, Enter gửi / Shift+Enter xuống dòng.
 * Khi đang stream → nút gửi chuyển thành nút "Dừng".
 */
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useChatStore } from "../../store/chatStore";
import { SendHorizontal, Square, Mic } from "lucide-react";

export function InputBar() {
  const [value, setValue] = useState("");
  const [isError, setIsError] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<any>(null);
  
  const sendMessage = useChatStore((s) => s.sendMessage);
  const stop = useChatStore((s) => s.stop);
  const isStreaming = useChatStore((s) => s.isStreaming);

  const triggerError = () => {
    setIsError(true);
    setTimeout(() => setIsError(false), 400);
  };

  // Khởi tạo SpeechRecognition
  useEffect(() => {
    // @ts-ignore
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'vi-VN';

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setValue((prev) => {
          const newVal = prev + (prev ? " " : "") + transcript;
          if (newVal.length > 1000) {
            triggerError();
            return newVal.slice(0, 1000);
          }
          return newVal;
        });
      };

      recognition.onerror = () => setIsRecording(false);
      recognition.onend = () => setIsRecording(false);
      recognitionRef.current = recognition;
    }
  }, []);

  const toggleRecording = () => {
    if (!recognitionRef.current) {
      alert("Trình duyệt của bạn không hỗ trợ tính năng nhận diện giọng nói.");
      return;
    }
    if (isRecording) {
      recognitionRef.current.stop();
    } else {
      recognitionRef.current.start();
      setIsRecording(true);
    }
  };

  // Auto-grow tối đa ~4 dòng
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    
    // Đợi 1 tick (sử dụng setTimeout) để đảm bảo DOM đã render xong nội dung chữ mới và có thể tính toán scrollHeight chính xác.
    const timeoutId = setTimeout(() => {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 120) + "px";
    }, 0);

    return () => clearTimeout(timeoutId);
  }, [value, isRecording]);

  const handleSend = () => {
    const text = value.trim();
    if (!text || isStreaming) return;
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    void sendMessage(text);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
      return;
    }
    // Cảnh báo nếu đang ở giới hạn mà vẫn gõ thêm ký tự (bỏ qua phím xoá, điều hướng...)
    if (
      value.length >= 1000 &&
      e.key.length === 1 &&
      !e.ctrlKey &&
      !e.metaKey &&
      !e.altKey
    ) {
      triggerError();
    }
  };

  const onPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const pasteData = e.clipboardData.getData("Text");
    if (value.length + pasteData.length > 1000) {
      triggerError();
    }
  };

  return (
    <div className="shrink-0 bg-white px-4 pb-2 pt-2 sm:rounded-b-2xl">
      <div
        className={`relative flex items-end gap-1 rounded-[24px] px-2 py-1.5 focus-within:ring-1 transition-all ${
          isError 
            ? "shake-error focus-within:ring-[var(--color-okbd)]" 
            : "bg-[#f3f4f6] focus-within:bg-[#f3f4f6] focus-within:ring-primary/20"
        }`}
      >
        {isRecording ? (
          <div className="flex flex-1 items-center justify-center min-h-[40px]">
            <div className="flex items-center gap-[3px] h-6">
              {[0.2, 0.5, 0.1, 0.8, 0.3, 0.6, 0.9, 0.4, 0.7, 0.2, 0.8, 0.3, 0.5, 0.1].map((delay, i) => (
                <div
                  key={i}
                  className="w-[3px] rounded-full bg-primary/70"
                  style={{ 
                    height: i % 2 === 0 ? '12px' : (i % 3 === 0 ? '20px' : '16px'),
                    animation: `sound-wave 1s ease-in-out infinite`,
                    animationDelay: `${delay}s` 
                  }}
                />
              ))}
            </div>
          </div>
        ) : (
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            onPaste={onPaste}
            rows={1}
            maxLength={1000}
            autoFocus
            placeholder="Nhập tin nhắn..."
            aria-label="Tin nhắn"
            className="scrollbar-hide max-h-[120px] flex-1 resize-none bg-transparent px-4 py-2 text-[15px] leading-relaxed text-ink outline-none placeholder:text-ink-soft/70"
          />
        )}
        
        {!isStreaming && (
          <button
            type="button"
            onClick={toggleRecording}
            aria-label={isRecording ? "Dừng ghi âm" : "Ghi âm giọng nói"}
            className={`group relative flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full transition-all duration-200 ${
              isRecording 
                ? "text-primary bg-primary/10 hover:bg-primary/20 active:scale-95" 
                : "text-ink/40 hover:text-primary hover:bg-primary/10 active:scale-95"
            }`}
          >
            {isRecording ? <Square size={16} fill="currentColor" strokeWidth={3} /> : <Mic size={23} strokeWidth={2} />}
            <span className="pointer-events-none absolute -top-8 z-50 hidden sm:block whitespace-nowrap rounded-md bg-ink/90 px-2 py-1 text-[11px] font-medium text-white opacity-0 shadow-sm transition-opacity group-hover:opacity-100">
              {isRecording ? "Dừng ghi âm" : "Ghi âm giọng nói"}
            </span>
          </button>
        )}

        {(isStreaming || value.trim()) && (
          <button
            type="button"
            onClick={isStreaming ? stop : handleSend}
            aria-label={isStreaming ? "Dừng" : "Gửi"}
            className={
              "group relative flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full transition-all duration-200 " +
              (isStreaming
                ? "text-primary bg-primary/10 hover:bg-primary/20 active:scale-95"
                : "text-primary hover:bg-primary/10 active:scale-95")
            }
          >
            {isStreaming ? (
              <Square size={16} fill="currentColor" strokeWidth={3} />
            ) : (
              <SendHorizontal size={24} />
            )}
            <span className="pointer-events-none absolute -top-8 right-0 z-50 hidden sm:block whitespace-nowrap rounded-md bg-ink/90 px-2 py-1 text-[11px] font-medium text-white opacity-0 shadow-sm transition-opacity group-hover:opacity-100">
              {isStreaming ? "Dừng" : "Gửi"}
            </span>
          </button>
        )}
      </div>
      <div className="mt-2 text-center text-[11px] font-medium text-ink-soft/60">
        Developed by <a href="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSmynwflXpkE-oKuOuxkYuKMBZ-QTq7BOgGNQ&s" target="_blank" rel="noopener noreferrer" className="font-bold"><span className="text-[#C72026]">V</span><span className="text-black"> - </span><span className="text-[#1D4179]">Internship</span></a> Core Team at <a href="https://vingroup.net/" target="_blank" rel="noopener noreferrer" className="font-bold"><span className="text-[#C72026]">Vin</span><span className="text-[#99002F]">Group</span></a>
      </div>
    </div>
  );
}
