"use client";

import { useEffect, useId, useRef, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { emptyProcesses, processSnapshot, subscribeProcesses } from "@/lib/processes";
import { useWorkspaceActivity } from "./process-indicator";
import { GhostArt } from "./ghost-art";
import "./ghost-mascot.css";

const durations = {blink: 280, doubleBlink: 650, lookAround: 2550, yawn: 2950,
  curious: 2450, happy: 1950, sleepy: 3450, surprised: 1650, dizzy: 2250};
type Expression = keyof typeof durations;
const idlePool: Expression[] = ["blink", "blink", "blink", "doubleBlink", "lookAround", "curious"];
const playfulPool: Expression[] = ["happy", "curious", "doubleBlink", "dizzy"];

/** An observational companion: never intercepts or changes workspace actions. */
export function GhostMascot({activityKey}: {activityKey: string}) {
  const root = useRef<HTMLButtonElement>(null);
  const id = useId().replace(/:/g, "");
  const cache = useQueryClient();
  const workspaceBusy = useWorkspaceActivity();
  const processes = useSyncExternalStore(subscribeProcesses, processSnapshot, emptyProcesses);
  const busy = workspaceBusy || processes.length > 0;
  const controller = useRef<{react: (name: Expression) => void; activity: () => void} | null>(null);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const rig = el.querySelector<SVGGElement>("[data-rig]")!;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const finePointer = window.matchMedia("(pointer: fine)");
    let state: Expression | "idle" = "idle";
    let resetTimer: ReturnType<typeof setTimeout>;
    let idleTimer: ReturnType<typeof setTimeout>;
    let frame = 0;
    let lastActivity = Date.now();
    let lastReaction = 0;
    let failedAt = 0;
    let x = 0;
    let y = 0;

    const schedule = () => {
      clearTimeout(idleTimer);
      if (document.hidden || motion.matches) return;
      idleTimer = setTimeout(() => {
        const resting = Date.now() - lastActivity > 45000;
        const pool: Expression[] = el.dataset.busy === "true" ? ["lookAround", "curious", "blink"]
          : resting ? [...idlePool, "yawn", "sleepy"] : idlePool;
        play(pool[Math.floor(Math.random() * pool.length)]);
      }, 4000 + Math.random() * 5000);
    };
    const play = (name: Expression) => {
      if (document.hidden || motion.matches) return;
      clearTimeout(resetTimer);
      clearTimeout(idleTimer);
      el.classList.remove(...Object.keys(durations).map(key => `state-${key}`));
      // Flush the previous expression so repeated blinks restart reliably.
      void el.offsetWidth;
      state = name;
      el.dataset.expression = name;
      el.classList.add(`state-${name}`);
      rig.style.transform = "";
      lastReaction = Date.now();
      resetTimer = setTimeout(() => {
        el.classList.remove(`state-${name}`);
        state = "idle";
        el.dataset.expression = "idle";
        schedule();
      }, durations[name]);
    };
    const activity = () => {lastActivity = Date.now();};
    const react = (name: Expression) => {
      activity();
      if (Date.now() - lastReaction > 1400 && (name !== "happy" || Date.now() - failedAt > 3000)) play(name);
    };
    controller.current = {react, activity};
    const pointer = (event: PointerEvent) => {
      if (event.pointerType !== "mouse" || !finePointer.matches || motion.matches || document.hidden) return;
      activity();
      x = event.clientX; y = event.clientY;
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (state !== "idle") return;
        const bounds = el.getBoundingClientRect();
        if (!bounds.width || !bounds.height || bounds.right <= 0) return;
        const dx = (x - bounds.left - bounds.width / 2) / (window.innerWidth * .35);
        const dy = (y - bounds.top - bounds.height / 2) / (window.innerHeight * .35);
        const scale = 1 / Math.max(1, Math.hypot(dx, dy));
        rig.style.transform = `translate(${dx * scale * 28}px, ${dy * scale * 22}px)`;
      });
    };
    const center = () => {rig.style.transform = "";};
    const click = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target || el.contains(target)) return;
      if (target.closest("button, a, summary, select, input[type=checkbox], input[type=radio]")) react("curious");
    };
    const input = () => react("curious");
    const invalid = () => {failedAt = Date.now(); react("surprised");};
    const visibility = () => {
      el.dataset.paused = String(document.hidden);
      clearTimeout(resetTimer); clearTimeout(idleTimer);
      cancelAnimationFrame(frame); frame = 0;
      el.classList.remove(...Object.keys(durations).map(key => `state-${key}`));
      el.dataset.expression = "idle";
      state = "idle"; center(); schedule();
    };
    const unsubscribeQueries = cache.getQueryCache().subscribe(event => {
      if (event.type === "updated" && event.action.type === "error") invalid();
    });
    const unsubscribeMutations = cache.getMutationCache().subscribe(event => {
      if (event.type !== "updated") return;
      if (event.action.type === "error") invalid();
      if (event.action.type === "success") react("happy");
    });
    window.addEventListener("pointermove", pointer, {passive: true});
    window.addEventListener("blur", center);
    document.documentElement.addEventListener("pointerleave", center);
    document.addEventListener("click", click, true);
    document.addEventListener("input", input, true);
    document.addEventListener("invalid", invalid, true);
    document.addEventListener("visibilitychange", visibility);
    motion.addEventListener("change", visibility);
    schedule();
    return () => {
      controller.current = null;
      clearTimeout(resetTimer); clearTimeout(idleTimer); cancelAnimationFrame(frame);
      unsubscribeQueries(); unsubscribeMutations();
      window.removeEventListener("pointermove", pointer);
      window.removeEventListener("blur", center);
      document.documentElement.removeEventListener("pointerleave", center);
      document.removeEventListener("click", click, true);
      document.removeEventListener("input", input, true);
      document.removeEventListener("invalid", invalid, true);
      document.removeEventListener("visibilitychange", visibility);
      motion.removeEventListener("change", visibility);
    };
  }, [cache]);

  const wasBusy = useRef(false);
  useEffect(() => {
    if (busy) controller.current?.react("curious");
    else if (wasBusy.current) controller.current?.react("doubleBlink");
    wasBusy.current = busy;
  }, [busy]);
  useEffect(() => {controller.current?.react("curious");}, [activityKey]);

  return <button ref={root} type="button" className="r-ghost" data-busy={busy}
    aria-label="Play with ghost companion" title={busy ? "Ghost is keeping you company while work runs" : "Say hello to your ghost companion"}
    onClick={() => controller.current?.react(playfulPool[Math.floor(Math.random() * playfulPool.length)])}>
    <span aria-hidden="true"><GhostArt id={`ghost-${id}`}/></span>
  </button>;
}
