"use client";

import { motion, useReducedMotion } from "framer-motion";
import { usePathname } from "next/navigation";

/**
 * Per-route template wrapper. Next.js re-mounts a `template.tsx` on
 * every route change (unlike `layout.tsx` which is preserved), so this
 * is the natural place to drop a soft entrance animation. The motion
 * is gated behind `prefers-reduced-motion` — when set, the route
 * paints instantly with no transform.
 */
export default function Template({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const reduced = useReducedMotion();
  return (
    <motion.div
      key={pathname ?? "root"}
      initial={reduced ? { opacity: 1, y: 0 } : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}
