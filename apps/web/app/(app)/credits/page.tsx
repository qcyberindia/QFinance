"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Moved into the Profile control center — kept so old links still work. */
export default function Redirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/profile/q-points"); }, [router]);
  return null;
}
