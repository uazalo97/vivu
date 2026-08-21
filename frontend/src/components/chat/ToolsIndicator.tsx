/**
 * Indicator "đang tra cứu" — xuất hiện khi agent gọi tool (get_price, search_kb...).
 */
export function ToolsIndicator({ tools }: { tools: string[] }) {
  if (!tools.length) return null;
  const last = tools[tools.length - 1];
  return (
    <div className="bubble-enter flex items-center gap-2 self-start rounded-2xl rounded-bl-md border border-chat-border bg-white px-3.5 py-2 text-[13px] text-ink-soft shadow-sm">
      <span className="spinner shrink-0" aria-hidden />
      <span>
        Đang tra cứu <span className="font-semibold text-primary">{last}</span>
        {tools.length > 1 && <span className="text-ink-soft/70"> +{tools.length - 1}</span>}
      </span>
    </div>
  );
}
