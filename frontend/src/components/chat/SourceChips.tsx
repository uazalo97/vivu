/**
 * Hiển thị nguồn tham khảo của câu trả lời (chips liên kết, mở tab mới).
 */
import { Link2 } from "lucide-react";
import type { Source } from "../../api/types";

export function SourceChips({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {sources.slice(0, 5).map((s, i) => (
        <a
          key={`${s.url}-${i}`}
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          title={s.url}
          className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-[#f3f4f6] px-2.5 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary-soft"
        >
          <Link2 size={12} className="shrink-0" />
          <span className="truncate">{s.text || s.url}</span>
        </a>
      ))}
    </div>
  );
}
