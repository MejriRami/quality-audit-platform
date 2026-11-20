import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router";
import { useSelector } from "react-redux";
import {
  ClipboardList,
  BookCheck,
  BarChart2,
  CalendarCheck,
  CalendarDays,
  CalendarRange,
  BadgeCheck,
  ListChecks,
  ShieldCheck,
} from "lucide-react";
import { ChevronDownIcon, HorizontaLDots, TableIcon } from "../icons";
import { useSidebar } from "../context/SidebarContext";
import logoNorthwindWide from "../assets/logo/logo-northwind.png";
import { RootState } from "../redux/store";
import {
  canManageFrameworks,
  canManagePlantHolidays,
  canPlanAudits,
  canViewExternalCertifications,
  hasAuditorRole,
  hasSystemAdminRole,
  isCertificationOnlyUser,
} from "../utils/roleAccess";

type NavItem = {
  name: string;
  icon: React.ReactNode;
  path?: string;
  requiresSystemAdmin?: boolean;
  requiresAuditor?: boolean;
  requiresFrameworkAccess?: boolean;
  requiresHolidayAccess?: boolean;
  requiresPlanningAccess?: boolean;
  requiresCertificationAccess?: boolean;
  subItems?: { name: string; path: string; pro?: boolean; new?: boolean }[];
};

const navItems: NavItem[] = [
  {
    name: "Framework",
    icon: <BookCheck className="w-[18px] h-[18px]" />,
    path: "/framework",
    requiresFrameworkAccess: true,
  },
  {
    name: "Questionnaires",
    icon: <ListChecks className="w-[18px] h-[18px]" />,
    path: "/questionnaire",
  },
  { name: "Audits", icon: <TableIcon />, path: "/audits" },
  {
    name: "Execute Audit",
    icon: <ClipboardList className="w-[18px] h-[18px]" />,
    path: "/fill",
    requiresAuditor: true,
  },
  {
    name: "Audits Calendar",
    icon: <CalendarCheck className="w-[18px] h-[18px]" />,
    path: "/audits-calendar",
  },
  // {
  //   name: "Audit Group Report",
  //   icon: <BarChart2 className="w-[18px] h-[18px]" />,
  //   path: "/kpi-audit-group-report",
  // },
  {
    name: "KPI Audits",
    icon: <BarChart2 className="w-[18px] h-[18px]" />,
    path: "/kpi-audits",
  },
  {
    name: "Admin Control Center",
    icon: <ShieldCheck className="w-[18px] h-[18px]" />,
    path: "/admin/control-center",
    requiresSystemAdmin: true,
  },
  {
    name: "Plant Holidays",
    icon: <CalendarDays className="w-[18px] h-[18px]" />,
    path: "/plant-holidays",
    requiresHolidayAccess: true,
  },
  {
    name: "Audit Planning",
    icon: <CalendarRange className="w-[18px] h-[18px]" />,
    path: "/audit-planning",
    requiresPlanningAccess: true,
  },
  {
    name: "External Certifications",
    icon: <BadgeCheck className="w-[18px] h-[18px]" />,
    path: "/external-certifications",
    requiresCertificationAccess: true,
  },
];

const othersItems: NavItem[] = [];

const AppSidebar: React.FC = () => {
  const { isExpanded, isMobileOpen, isHovered, setIsHovered } = useSidebar();
  const location = useLocation();
  const roles = useSelector((s: RootState) => s.auth.role || []);
  const isSystemAdmin = hasSystemAdminRole(roles);
  const isAuditor = hasAuditorRole(roles);
  const hasFrameworkAccess = canManageFrameworks(roles);
  const hasHolidayAccess = canManagePlantHolidays(roles);
  const hasPlanningAccess = canPlanAudits(roles);
  const hasCertificationAccess = canViewExternalCertifications();
  const certificationOnly = isCertificationOnlyUser(roles);
  const visibleNavItems = navItems.filter((item) =>
    certificationOnly
      ? item.requiresCertificationAccess
      : item.requiresSystemAdmin
      ? isSystemAdmin
      : item.requiresAuditor
        ? isAuditor
        : item.requiresFrameworkAccess
          ? hasFrameworkAccess
          : item.requiresHolidayAccess
            ? hasHolidayAccess
            : item.requiresPlanningAccess
              ? hasPlanningAccess
              : item.requiresCertificationAccess
                ? hasCertificationAccess
                : true,
  );

  const [openSubmenu, setOpenSubmenu] = useState<{
    type: "main" | "others";
    index: number;
  } | null>(null);
  const [subMenuHeight, setSubMenuHeight] = useState<Record<string, number>>(
    {},
  );
  const subMenuRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const isActive = useCallback(
    (path: string) => location.pathname === path,
    [location.pathname],
  );

  useEffect(() => {
    let submenuMatched = false;
    ["main", "others"].forEach((menuType) => {
      const items = menuType === "main" ? visibleNavItems : othersItems;
      items.forEach((nav, index) => {
        if (nav.subItems) {
          nav.subItems.forEach((subItem) => {
            if (isActive(subItem.path)) {
              setOpenSubmenu({ type: menuType as "main" | "others", index });
              submenuMatched = true;
            }
          });
        }
      });
    });
    if (!submenuMatched) setOpenSubmenu(null);
  }, [location, isActive, visibleNavItems]);

  useEffect(() => {
    if (openSubmenu !== null) {
      const key = `${openSubmenu.type}-${openSubmenu.index}`;
      if (subMenuRefs.current[key]) {
        setSubMenuHeight((prev) => ({
          ...prev,
          [key]: subMenuRefs.current[key]?.scrollHeight || 0,
        }));
      }
    }
  }, [openSubmenu]);

  const handleSubmenuToggle = (index: number, menuType: "main" | "others") => {
    setOpenSubmenu((prev) => {
      if (prev && prev.type === menuType && prev.index === index) return null;
      return { type: menuType, index };
    });
  };

  const sidebarExpanded = isExpanded || isHovered || isMobileOpen;

  const renderMenuItems = (items: NavItem[], menuType: "main" | "others") => (
    <ul className="flex flex-col gap-1">
      {items.map((nav, index) => {
        const isOpen =
          openSubmenu?.type === menuType && openSubmenu?.index === index;

        return (
          <li key={nav.name}>
            {nav.subItems ? (
              <button
                onClick={() => handleSubmenuToggle(index, menuType)}
                className={`
                  flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-150
                  ${
                    isOpen
                      ? "bg-slate-800/70 text-white ring-1 ring-white/10"
                      : "text-slate-300/80 hover:bg-white/5 hover:text-white"
                  }
                  ${!sidebarExpanded ? "lg:justify-center" : ""}
                `}
              >
                <span
                  className={`shrink-0 ${isOpen ? "text-white" : "text-slate-400"}`}
                >
                  {nav.icon}
                </span>
                {sidebarExpanded && (
                  <span className="flex-1 text-left">{nav.name}</span>
                )}
                {sidebarExpanded && (
                  <ChevronDownIcon
                    className={`w-4 h-4 shrink-0 transition-transform duration-200 ${isOpen ? "rotate-180 text-white" : "text-slate-400"}`}
                  />
                )}
              </button>
            ) : (
              nav.path && (
                <Link
                  to={nav.path}
                  className={`
                    flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-150
                    ${
                      isActive(nav.path)
                        ? "bg-white/10 text-white ring-1 ring-white/10"
                        : "text-slate-300/80 hover:bg-white/5 hover:text-white"
                    }
                    ${!sidebarExpanded ? "lg:justify-center" : ""}
                  `}
                >
                  <span
                    className={`shrink-0 ${isActive(nav.path) ? "text-white" : "text-slate-400"}`}
                  >
                    {nav.icon}
                  </span>
                  {sidebarExpanded && <span>{nav.name}</span>}

                  {isActive(nav.path) && sidebarExpanded && (
                    <span className="ml-auto h-4 w-[3px] rounded-full bg-slate-200/80" />
                  )}
                </Link>
              )
            )}

            {nav.subItems && sidebarExpanded && (
              <div
                ref={(el) => {
                  subMenuRefs.current[`${menuType}-${index}`] = el;
                }}
                className="overflow-hidden transition-all duration-300"
                style={{
                  height: isOpen
                    ? `${subMenuHeight[`${menuType}-${index}`]}px`
                    : "0px",
                }}
              >
                <ul className="mt-1 ml-[38px] space-y-0.5 border-l border-white/10 pb-1 pl-3">
                  {nav.subItems.map((subItem) => (
                    <li key={subItem.name}>
                      <Link
                        to={subItem.path}
                        className={`block rounded-md px-2 py-2 text-sm transition-colors duration-150 ${
                          isActive(subItem.path)
                            ? "font-medium text-white"
                            : "text-slate-300/60 hover:text-white"
                        }`}
                      >
                        {subItem.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );

  return (
    <aside
      className={`
        fixed top-0 left-0 flex flex-col
        mt-16 lg:mt-0
        h-screen
        bg-slate-950/95
        border-r border-slate-800/70
        transition-all duration-300 ease-in-out
        z-[60] shadow-[2px_0_14px_0_rgba(2,6,23,0.22)]
        ${isExpanded || isMobileOpen ? "w-[230px]" : isHovered ? "w-[230px]" : "w-[70px]"}
        ${isMobileOpen ? "translate-x-0" : "-translate-x-full"}
        lg:translate-x-0
      `}
      onMouseEnter={() => !isExpanded && setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className="hidden h-16 shrink-0 items-center justify-center border-b border-slate-800/70 px-4 lg:flex">
        {sidebarExpanded ? (
          <Link to="/" className="block">
            <img
              src={logoNorthwindWide}
              alt="Northwind Group"
              className="h-8 w-auto object-contain"
            />
          </Link>
        ) : (
          <Link to="/" className="block">
            <img
              src={logoNorthwindWide}
              alt="Northwind Group"
              className="h-6 w-auto object-contain"
            />
          </Link>
        )}
      </div>

      <div className="flex-1 overflow-y-auto no-scrollbar px-3 py-4">
        <nav>
          <div
            className={`mb-2 flex px-2 ${!sidebarExpanded ? "lg:justify-center" : ""}`}
          >
            {sidebarExpanded ? (
              <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-300/60">
                Primary
              </span>
            ) : (
              <HorizontaLDots className="size-5 text-slate-300/70" />
            )}
          </div>

          {renderMenuItems(visibleNavItems, "main")}
          {renderMenuItems(othersItems, "others")}
        </nav>
      </div>

      <div className="shrink-0 border-t border-slate-800/70">
        <div className="h-1 w-full bg-white/5" />
      </div>
    </aside>
  );
};

export default AppSidebar;
