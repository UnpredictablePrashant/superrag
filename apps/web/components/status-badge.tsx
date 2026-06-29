import { Badge } from "@rag-console/ui";
import React from "react";

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase();
  const tone =
    normalized.includes("COMPLETED") ? "green" : normalized.includes("FAILED") || normalized.includes("CANCELLED")
      ? "red"
      : normalized.includes("REVIEW") || normalized.includes("QUEUED")
        ? "amber"
        : "blue";
  return <Badge tone={tone}>{status.replaceAll("_", " ")}</Badge>;
}
