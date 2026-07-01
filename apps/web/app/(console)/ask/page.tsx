import { redirect } from "next/navigation";

export default function AskPage() {
  redirect("/chat?mode=ai");
}
