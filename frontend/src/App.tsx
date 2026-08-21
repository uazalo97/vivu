import { BrowserRouter, Routes, Route } from "react-router-dom";
import { LandingPage } from "./components/landing/LandingPage";
import { ChatWidget } from "./components/chat";
import AdminDashboard from "./pages/admin/AdminDashboard";

function LandingWithChat() {
  return (
    <div className="relative min-h-screen bg-white">
      <LandingPage />
      <ChatWidget />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/*" element={<LandingWithChat />} />
      </Routes>
    </BrowserRouter>
  );
}
