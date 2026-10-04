export type StudioFlavor = "original" | "editorial" | "pixel" | "collage";

export const studioFlavors: { id: StudioFlavor; name: string; note: string; eyebrow: string; first: string; second: string; description: string }[] = [
  { id: "editorial", name: "01 · 灵感编辑部", note: "钴蓝 × 酸橙 · 清爽有锋芒", eyebrow: "GOOD WORK. A LITTLE PLAY.", first: "认真搞定，", second: "也要有点好玩。", description: "把琐碎交给搭子，把好奇心留给自己。" },
  { id: "pixel", name: "02 · 数字游乐场", note: "像素 × 电光绿 · 轻复古科技感", eyebrow: "HELLO, HUMAN_ / READY TO CREATE", first: "你的灵感，", second: "即刻上线。", description: "给灵感一个入口，给今天一个漂亮的进度条。" },
  { id: "collage", name: "03 · 贴纸创作室", note: "纸感 × 珊瑚粉 · 松弛有温度", eyebrow: "A SMALL STUDIO FOR BIG IDEAS", first: "把好点子，", second: "贴进今天。", description: "收集灵感，慢慢展开。今天也做一点喜欢的事。" },
  { id: "original", name: "原版 · 活力创作", note: "原有紫色方案，方便对照", eyebrow: "MAKE ROOM FOR GOOD WORK.", first: "好想法，", second: "现在就开始。", description: "写一份好文案，读懂一张表，完成下一件事。" },
];

export function StudioArtwork({ flavor, className }: { flavor: StudioFlavor; className: string }) {
  if (flavor === "original") return null;
  return <div className={className} aria-hidden="true">
    <svg viewBox="0 0 340 206" fill="none">
      {flavor === "editorial" ? <>
        <ellipse cx="175" cy="181" rx="126" ry="10" fill="#deded3" opacity=".45" />
        <g transform="translate(81 15) rotate(-12 79 80)">
          <path d="M80 0c31 0 45 18 41 42 24-5 43 10 43 39s-19 44-43 39c4 24-10 43-41 43s-44-19-40-43C16 125 0 110 0 81s16-44 40-39C36 18 49 0 80 0Z" fill="#365cf6" />
          <ellipse cx="64" cy="74" rx="6" ry="12" fill="#fff" /><ellipse cx="101" cy="74" rx="6" ry="12" fill="#fff" />
          <path d="M60 103q24 23 46-1" stroke="#fff" strokeWidth="5" strokeLinecap="round" />
        </g>
        <g transform="rotate(13 264 44)"><rect x="218" y="23" width="100" height="34" rx="17" fill="#dbf75b" stroke="#252b19" /><text x="268" y="44" textAnchor="middle" fill="#252b19" fontFamily="monospace" fontSize="12" fontWeight="700">IDEA CLUB ↗</text></g>
        <path d="m55 126 7 21 22 4-20 10-2 22-13-19-22 4 14-17-8-20Z" fill="#ff895f" />
        <path d="m272 115 12 7-8 17m-2-31c38 13 21 67-15 68" stroke="#3c3b37" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="3 4" />
      </> : flavor === "pixel" ? <>
        <path d="M32 27h30M47 12v30M290 153h30M305 138v30" stroke="#777483" strokeWidth="1.5" />
        <g transform="translate(85 15)">
          <path d="M36 0h114v12h24v24h12v108h-12v24h-24v12H36v-12H12v-24H0V36h12V12h24Z" fill="#292636" />
          <path d="M38 7h110v12h20v23h11v97h-11v23h-20v11H38v-11H18v-23H7V42h11V19h20Z" fill="#d6ff82" />
          <path d="M45 52h17v32H45zm78 0h17v32h-17zM58 112h18v13h36v-13h18v26H58Z" fill="#30283e" />
          <path d="M31 33h16M23 41v16" stroke="#f3ffe0" strokeWidth="5" />
        </g>
        <g transform="rotate(-9 262 49)"><rect x="232" y="34" width="79" height="31" fill="#b5a1f5" stroke="#35303d" strokeWidth="2" /><text x="271" y="54" textAnchor="middle" fontFamily="monospace" fontSize="12" fill="#262132">100% YOU</text></g>
        <rect x="33" y="139" width="57" height="33" fill="#fff" stroke="#35303d" strokeWidth="2" /><path d="m45 149 8 6-8 6m15 0h15" stroke="#35303d" strokeWidth="2" />
        <path d="M293 88v27m-13-14h27" stroke="#ff976e" strokeWidth="7" />
      </> : <>
        <g transform="rotate(9 155 104)">
          <rect x="90" y="32" width="135" height="155" rx="3" fill="#ddd5c3" />
          <rect x="86" y="27" width="135" height="155" rx="3" fill="#fffdf2" stroke="#373429" strokeWidth="1.4" />
          <path d="M102 117h101m-101 20h83m-83 20h94" stroke="#dcd8ca" />
          <text x="106" y="63" fontFamily="Georgia,serif" fontSize="25" fontStyle="italic" fill="#313126">good work,</text>
          <text x="103" y="91" fontFamily="Georgia,serif" fontSize="25" fontStyle="italic" fill="#313126">good mood.</text>
        </g>
        <path d="m130 12 70 8-6 27-67-9Z" fill="#c6d5f6" opacity=".8" />
        <g transform="translate(55 105) rotate(-16)">
          {Array.from({length:8},(_,i)=><ellipse key={i} cx="0" cy="-29" rx="18" ry="25" fill="#fca98b" stroke="#774c37" strokeWidth=".7" transform={`rotate(${i*45})`} />)}
          <circle r="27" fill="#ffdb65" stroke="#774c37" /><circle cx="-9" cy="-5" r="3" fill="#573d30" /><circle cx="9" cy="-5" r="3" fill="#573d30" /><path d="M-10 8q10 12 20 0" stroke="#573d30" strokeWidth="2" strokeLinecap="round" />
        </g>
        <g transform="rotate(-13 261 141)"><rect x="211" y="123" width="107" height="34" rx="3" fill="#dce990" stroke="#5d6435" /><text x="264" y="145" textAnchor="middle" fill="#3d4521" fontFamily="monospace" fontSize="13" fontWeight="700">MADE BY YOU</text></g>
        <path d="m267 32 6 17 19 4-17 9-1 19-12-15-19 2 12-15-7-17Z" fill="#8f8dc8" stroke="#666080" />
      </>}
    </svg>
  </div>;
}
