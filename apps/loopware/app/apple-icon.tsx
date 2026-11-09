import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#070b12",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <svg width="140" height="140" viewBox="0 0 64 64">
          <path
            d="M46 24a16 16 0 1 0 2 10"
            fill="none"
            stroke="#38d1ff"
            strokeWidth="7"
            strokeLinecap="round"
          />
          <path d="M40 13l8 11-13 2z" fill="#38d1ff" />
          <circle cx="32" cy="32" r="5.5" fill="#ffb547" />
        </svg>
      </div>
    ),
    size,
  );
}
