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
  X,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "대시보드", icon: LayoutDashboard },
  { href: "/history", label: "히스토리", icon: History },
  { href: "/alerts", label: "알림 설정", icon: Bell },
];

interface SidebarProps {
  isDesktop: boolean;
  isOpen: boolean;
  onClose: () => void;
}

export default function Sidebar({ isDesktop, isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  const isCoinPage = pathname.startsWith("/coin/");

  // 모바일: 오버레이 드로어
  if (!isDesktop) {
    if (!isOpen) return null;

    return (
      <>
        {/* 백드롭 */}
        <div className="backdrop-overlay" onClick={onClose} />

        {/* 드로어 */}
        <aside className="fixed top-0 left-0 h-full z-50 w-[260px] bg-sidebar-bg shadow-sidebar animate-slide-left flex flex-col">
          {/* 로고 + 닫기 */}
          <div
            className="flex items-center justify-between px-5 bg-card-active shrink-0"
            style={{ height: "var(--header-height)" }}
          >
            <div className="flex items-center gap-2.5">
              <BarChart3 size={22} className="text-primary shrink-0" />
              <span className="text-base font-semibold text-heading tracking-tight">
                CryptoSignal
              </span>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-card text-icon-muted hover:text-heading hover:bg-card-active transition-colors"
            >
              <X size={18} />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 mt-4 px-3">
            <ul className="space-y-1">
              {NAV_ITEMS.map((item) => {
                const active = isActive(item.href) || (item.href === "/" && isCoinPage);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onClose}
                      className={`flex items-center gap-3 px-3 py-2.5 text-sm font-medium rounded-card transition-colors ${
                        active
                          ? "text-primary bg-primary/10"
                          : "text-body-text hover:text-heading hover:bg-card-active"
                      }`}
                    >
                      <Icon size={18} className={active ? "text-primary" : "text-icon-muted"} />
                      <span>{item.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </aside>
      </>
    );
  }

  // 데스크톱: 고정 사이드바
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
      <nav className="flex-1 mt-4 px-2">
        <ul className="space-y-1">
          {NAV_ITEMS.map((item) => {
            const active = isActive(item.href) || (item.href === "/" && isCoinPage);
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`flex items-center gap-3 py-2.5 text-sm font-medium rounded-card transition-colors ${
                    collapsed ? "justify-center px-0" : "px-3"
                  } ${
                    active
                      ? "text-primary bg-primary/10"
                      : "text-body-text hover:text-heading hover:bg-card-active"
                  }`}
                >
                  <Icon size={18} className={active ? "text-primary" : "text-icon-muted"} />
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
