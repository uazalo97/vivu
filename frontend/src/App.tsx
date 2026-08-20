/**
 * App mặc định: Landing page (trắng) + ChatWidget nhúng nổi.
 * ChatWidget hoàn toàn độc lập — có thể lấy ra dùng riêng trên trang chính thức.
 */
import { LandingPage } from "./components/landing/LandingPage";
import { ChatWidget } from "./components/chat";

export default function App() {
  return (
    <div className="relative min-h-screen bg-white">
      <LandingPage />
      <ChatWidget />
    </div>
  );
}
