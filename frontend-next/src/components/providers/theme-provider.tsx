"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

export type AppTheme = "default" | "dark" | "light";

interface ThemeContextType {
  theme: AppTheme;
  setTheme: (theme: AppTheme) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: "default",
  setTheme: () => {},
});

const THEME_STORAGE_KEY = "atos_app_theme";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>("default");
  const [mounted, setMounted] = useState(false);

  const applyTheme = (newTheme: AppTheme) => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    const body = document.body;

    root.setAttribute("data-theme", newTheme);
    if (body) {
      body.setAttribute("data-theme", newTheme);
    }

    if (newTheme === "light") {
      root.classList.remove("dark");
      root.classList.add("light");
    } else {
      root.classList.remove("light");
      root.classList.add("dark");
    }

    // Broadcast change for any multi-window or auxiliary listeners
    window.dispatchEvent(
      new CustomEvent("atos:theme-changed", { detail: { theme: newTheme } })
    );
  };

  useEffect(() => {
    try {
      const stored = localStorage.getItem(THEME_STORAGE_KEY) as AppTheme | null;
      if (stored && (stored === "default" || stored === "dark" || stored === "light")) {
        setThemeState(stored);
        applyTheme(stored);
      } else {
        applyTheme("default");
      }
    } catch {
      applyTheme("default");
    }
    setMounted(true);
  }, []);

  const setTheme = (newTheme: AppTheme) => {
    setThemeState(newTheme);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, newTheme);
    } catch (e) {
      console.warn("Failed saving theme to localStorage:", e);
    }
    applyTheme(newTheme);
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
