"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
	LayoutDashboard,
	Layers,
	Key,
	FlaskConical,
	ScrollText,
	BarChart3,
	FileText,
	X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/lib/store/uiStore";

const navItems = [
	{ label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
	{ label: "Integrations", href: "/integrations", icon: Layers },
	{ label: "API Keys", href: "/api-keys", icon: Key },
	{ label: "Eval Runs", href: "/eval", icon: FlaskConical },
	{ label: "Audit Logs", href: "/audit-logs", icon: ScrollText },
	{ label: "Usage", href: "/usage", icon: BarChart3 },
	{ label: "Prompts", href: "/prompts", icon: FileText },
];

export function Sidebar() {
	const pathname = usePathname();
	const { sidebarOpen, closeSidebar } = useUiStore();

	// Close drawer on route change
	useEffect(() => {
		closeSidebar();
	}, [pathname, closeSidebar]);

	// Lock body scroll when drawer is open on mobile
	useEffect(() => {
		if (sidebarOpen) {
			document.body.style.overflow = "hidden";
		} else {
			document.body.style.overflow = "";
		}
		return () => {
			document.body.style.overflow = "";
		};
	}, [sidebarOpen]);

	return (
		<>
			{/* Mobile overlay */}
			<div
				onClick={closeSidebar}
				className={cn(
					"lg:hidden fixed inset-0 z-40 bg-black/50 transition-opacity duration-200",
					sidebarOpen
						? "opacity-100 pointer-events-auto"
						: "opacity-0 pointer-events-none",
				)}
				aria-hidden="true"
			/>

			<aside
				className={cn(
					"fixed lg:static inset-y-0 left-0 z-50 w-64 flex-shrink-0 bg-[#111827] flex flex-col h-full",
					"transform transition-transform duration-200 ease-out",
					sidebarOpen
						? "translate-x-0"
						: "-translate-x-full lg:translate-x-0",
				)}
				aria-label="Primary navigation"
			>
				{/* Logo */}
				<div className="h-16 flex items-center justify-between px-6 border-b border-white/10">
					<Link
						href="/dashboard"
						className="flex items-center gap-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#111827] focus-visible:ring-[#3B82F6]"
						onClick={closeSidebar}
						aria-label="RAGfier home"
					>
						<span className="text-xl font-extrabold text-white tracking-tight">
							RAGfier
						</span>
						<span className="w-2 h-2 rounded-full bg-[#3B82F6] ml-0.5 mt-0.5" />
					</Link>
					<button
						onClick={closeSidebar}
						className="lg:hidden p-2 rounded-md text-gray-300 hover:bg-white/10 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#111827] focus-visible:ring-[#3B82F6]"
						aria-label="Close navigation"
					>
						<X className="h-5 w-5" />
					</button>
				</div>

				{/* Navigation */}
				<nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
					{navItems.map(({ label, href, icon: Icon }) => {
						const isActive =
							pathname === href || pathname.startsWith(href + "/");
						return (
							<Link
								key={href}
								href={href}
								className={cn(
									"flex items-center gap-3 px-4 py-3 text-sm font-medium rounded-md transition-colors duration-150",
									"focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#111827] focus-visible:ring-[#3B82F6]",
									isActive
										? "bg-[#3B82F6] text-white"
										: "text-gray-300 hover:bg-white/10",
								)}
								aria-current={isActive ? "page" : undefined}
							>
								<Icon className="h-4 w-4 flex-shrink-0" />
								<span>{label}</span>
							</Link>
						);
					})}
				</nav>

				{/* Footer */}
				<div className="px-6 py-4 border-t border-white/10">
					<p className="text-xs text-gray-500">RAGfier v0.1.0</p>
				</div>
			</aside>
		</>
	);
}
