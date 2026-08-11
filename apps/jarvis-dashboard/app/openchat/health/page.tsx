import { redirect } from "next/navigation";

/** 旧URL。健全性は /openchat 上部に統合済み */
export default function OpenchatHealthRedirect() {
  redirect("/openchat");
}
