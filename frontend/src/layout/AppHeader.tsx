import { useEffect, useRef, useState } from "react";
import { useSidebar } from "../context/SidebarContext";
import { ThemeToggleButton } from "../components/common/ThemeToggleButton";
import UserDropdown from "../components/header/UserDropdown";
import NotificationDropdown from "../components/header/NotificationDropdown";

const AppHeader: React.FC = () => {
  const [isApplicationMenuOpen, setApplicationMenuOpen] = useState(false);
  const { isMobileOpen, toggleSidebar, toggleMobileSidebar } = useSidebar();

  const handleToggle = () => {
    if (window.innerWidth >= 1024) {
      toggleSidebar();
    } else {
      toggleMobileSidebar();
    }
  };

  const toggleApplicationMenu = () => {
    setApplicationMenuOpen(!isApplicationMenuOpen);
  };

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <header className="sticky top-0 z-30 flex w-full items-center border-b border-slate-200/70 bg-white/80 backdrop-blur supports-[backdrop-filter]:bg-white/70 dark:border-slate-800/80 dark:bg-slate-950/70">
      <div className="relative flex h-[62px] flex-1 items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-3">
          <button
            onClick={handleToggle}
            aria-label="Toggle Sidebar"
            className="flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {isMobileOpen ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  fillRule="evenodd"
                  clipRule="evenodd"
                  d="M6.22 7.28a1 1 0 011.42-1.41L12 10.59l4.36-4.72a1 1 0 011.42 1.41L13.06 12l4.72 4.72a1 1 0 01-1.42 1.41L12 13.41l-4.36 4.72a1 1 0 01-1.42-1.41L10.94 12 6.22 7.28z"
                  fill="currentColor"
                />
              </svg>
            ) : (
              <svg width="16" height="12" viewBox="0 0 16 12" fill="none">
                <path
                  fillRule="evenodd"
                  clipRule="evenodd"
                  d="M0.583 1C0.583.586.919.25 1.333.25H14.667c.414 0 .75.336.75.75s-.336.75-.75.75H1.333C.919 1.75.583 1.414.583 1zm0 10c0-.414.336-.75.75-.75h13.334c.414 0 .75.336.75.75s-.336.75-.75.75H1.333c-.414 0-.75-.336-.75-.75zM1.333 5.25c-.414 0-.75.336-.75.75s.336.75.75.75H8c.414 0 .75-.336.75-.75s-.336-.75-.75-.75H1.333z"
                  fill="currentColor"
                />
              </svg>
            )}
          </button>
        </div>

        <div className="hidden items-baseline gap-2 lg:flex">
          <span className="font-['Outfit',sans-serif] text-base font-semibold tracking-[0.01em] text-slate-900 dark:text-white">
            Northwind
          </span>
          <span className="text-sm font-medium text-slate-500 dark:text-slate-400">
            Audit Workspace
          </span>
        </div>

        <div
          className={`${
            isApplicationMenuOpen ? "flex" : "hidden"
          } items-center gap-3 lg:flex`}
        >
          <ThemeToggleButton />
          <NotificationDropdown />
          <UserDropdown />
        </div>

        <button
          onClick={toggleApplicationMenu}
          className="flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 lg:hidden dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <circle cx="5" cy="12" r="1.5" fill="currentColor" />
            <circle cx="12" cy="12" r="1.5" fill="currentColor" />
            <circle cx="19" cy="12" r="1.5" fill="currentColor" />
          </svg>
        </button>
      </div>
    </header>
  );
};

export default AppHeader;
