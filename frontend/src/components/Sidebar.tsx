"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  History,
  Bell,
  ChevronLeft,
  ChevronRight,
  BarChart3,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "대시보드", icon: LayoutDashboard },
  { href: "/history", label: "히스토리", icon: History },
  { href: "/alerts", label: "알림 설정", icon: Bell },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  // 코인 상세 페이지에서도 대시보드 활성
  const isCoinPage = pathname.startsWith("/coin/");

  return (
    <aside
      className={`fixed top-0 left-0 h-full z-40 bg-sidebar-bg shadow-sidebar transition-all duration-200 flex flex-col ${
        collapsed ? "w-sidebar-collapsed" : "w-sidebar"
      }`}
    >
      {/* Logo */}
      <div
        className="flex items-center bg-card-active shrink-0"
        style={{ height: "var(--header-height)" }}
      >
        <div
          className={`flex items-center ${
            collapsed ? "justify-center w-full" : "px-5"
          } gap-2.5`}
        >
          <BarChart3 size={22} className="text-primary shrink-0" />
          {!collapsed && (
            <span className="text-base font-semibold text-heading whitespace-nowrap tracking-tight">
              CryptoSignal
            </span>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 mt-6 px-0">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const active =
              isActive(item.href) || (item.href === "/" && isCoinPage);
            const Icon = item.icon;
            return (
              <li
                key={item.href}
                className={active ? "bg-sidebar-active" : ""}
              >
                <Link
                  href={item.href}
                  className={`flex items-center gap-3 py-2.5 text-sm font-medium transition-colors ${
                    collapsed ? "justify-center px-0" : "px-5"
                  } ${
                    active
                      ? "text-sidebar-accent border-l-[3px] border-sidebar-accent"
                      : "text-body-text border-l-[3px] border-transparent hover:text-sidebar-accent"
                  }`}
                >
                  <Icon
                    size={18}
                    className={
                      active ? "text-sidebar-accent" : "text-icon-muted"
                    }
                  />
                  {!collapsed && <span>{item.label}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="p-3 flex items-center justify-center text-icon-muted hover:text-heading transition-colors border-t"
        style={{ borderColor: "var(--border)" }}
      >
        {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
    </aside>
  );
}
