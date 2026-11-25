"use client";
/** 判断するお題が残っていないときの表示（輪とチェックが描かれ、粒がはじける） */
export default function AllClear({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="glass card allclear" role="status">
      <div className="ac-art" aria-hidden="true">
        <svg className="ac-ring" width="84" height="84" viewBox="0 0 84 84">
          <circle className="ac-ring-bg" cx="42" cy="42" r="36" />
          <circle className="ac-ring-fg" cx="42" cy="42" r="36" />
          <path className="ac-check" d="M27 43 L38 54 L58 31" />
        </svg>
        {Array.from({ length: 16 }, (_, i) => (
          <i key={i} className={`ac-spark c${i % 4}`} style={{ ["--a" as string]: `${i * 22.5}deg` }} />
        ))}
      </div>
      <span aria-hidden="true">{Array.from({ length: 12 }, (_, i) => (
          <i key={`f${i}`} className={`ac-fall c${i % 4}`} style={{ left: `${4 + i * 8}%`, animationDelay: `${(i % 6) * 0.25}s` }} />
        ))}</span>
      <strong className="ac-title">{title}</strong>
      <span className="ac-sub">{sub}</span>
    </div>
  );
}

