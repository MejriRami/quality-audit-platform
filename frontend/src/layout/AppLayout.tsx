import { SidebarProvider, useSidebar } from "../context/SidebarContext";
import { Outlet } from "react-router";
import AppHeader from "./AppHeader";
import Backdrop from "./Backdrop";
import AppSidebar from "./AppSidebar";
import AuditorAssistant from "../components/chatbot/AuditorAssistant";

const LayoutContent: React.FC = () => {
  const { isExpanded, isHovered, isMobileOpen } = useSidebar();

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-50">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_-10%,rgba(30,58,138,0.10),transparent_45%),radial-gradient(circle_at_90%_-20%,rgba(14,116,144,0.08),transparent_42%),linear-gradient(180deg,rgba(15,23,42,0.02),transparent_32%)] dark:bg-[radial-gradient(circle_at_12%_-10%,rgba(148,163,184,0.12),transparent_45%),radial-gradient(circle_at_90%_-20%,rgba(56,189,248,0.10),transparent_46%),linear-gradient(180deg,rgba(15,23,42,0.35),transparent_36%)]" />
      <AppSidebar />
      <Backdrop />
      <div
        className={`relative flex-1 transition-all duration-300 ease-in-out ${
          isExpanded
            ? "lg:ml-[230px]"
            : isHovered
              ? "lg:ml-[230px]"
              : "lg:ml-[70px]"
        } ${isMobileOpen ? "ml-0" : ""}`}
      >
        <AppHeader />
        <div className="mx-auto max-w-(--breakpoint-2xl) px-4 pb-10 pt-6 md:px-8">
          <Outlet />
        </div>
      </div>
      <AuditorAssistant />
    </div>
  );
};

const AppLayout: React.FC = () => {
  return (
    <SidebarProvider>
      <LayoutContent />
    </SidebarProvider>
  );
};

export default AppLayout;
