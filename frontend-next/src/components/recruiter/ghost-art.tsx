/* SVG artwork adapted from the supplied Ghost Orb Animation Studio. */
export function GhostArt({id}: {id: string}) {
  return (<svg viewBox="0 0 300 300" className="ghost-svg w-full h-full" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <clipPath id={`${id}-orb-clip`}>
            <circle cx="150" cy="150" r="138" />
          </clipPath>
          <radialGradient id={`${id}-orb-body-grad`} cx="42%" cy="38%" r="60%" fx="32%" fy="28%">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="62%" stopColor="#ffffff" />
            <stop offset="84%" stopColor="#e9f0fc" />
            <stop offset="95%" stopColor="#cedcf6" />
            <stop offset="100%" stopColor="#bdcef1" />
          </radialGradient>
          <linearGradient id={`${id}-orb-rim-grad`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0" />
            <stop offset="75%" stopColor="#b7caef" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#9cb5e8" stopOpacity="0.55" />
          </linearGradient>
          <linearGradient id={`${id}-eye-fill-grad`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#05070b" />
            <stop offset="58%" stopColor="#101520" />
            <stop offset="86%" stopColor="#2c374b" />
            <stop offset="100%" stopColor="#5d6d87" />
          </linearGradient>
          <linearGradient id={`${id}-eye-rim-grad`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#000000" />
            <stop offset="100%" stopColor="#1a202c" />
          </linearGradient>
          <radialGradient id={`${id}-blush-grad`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ff8da6" stopOpacity="0.65" />
            <stop offset="100%" stopColor="#ff8da6" stopOpacity="0" />
          </radialGradient>
          <filter id={`${id}-orb-shadow`} x="-15%" y="-15%" width="130%" height="135%">
            <feDropShadow dx="0" dy="10" stdDeviation="12" floodColor="#0f172a" floodOpacity="0.28" />
          </filter>
        </defs>
        <g filter={`url(#${id}-orb-shadow)`}>
          <circle cx="150" cy="150" r="138" fill={`url(#${id}-orb-body-grad)`} />
          <circle cx="150" cy="150" r="138" fill={`url(#${id}-orb-rim-grad)`} />
          <circle cx="150" cy="150" r="137.2" fill="none" stroke="#c3d3f4" strokeWidth="1.5" opacity="0.85" />
        </g>
        <g clipPath={`url(#${id}-orb-clip)`}>
          <g className="ghost-idle-float">
            <g className="ghost-face-rig" data-rig="face">
              <ellipse className="ghost-blush" cx="72" cy="176" rx="24" ry="13" fill={`url(#${id}-blush-grad)`} />
              <ellipse className="ghost-blush" cx="228" cy="176" rx="24" ry="13" fill={`url(#${id}-blush-grad)`} />
              <g className="ghost-mouth">
                <ellipse cx="150" cy="205" rx="18" ry="23" fill="#121723" stroke="#05070b" strokeWidth="2" />
                <path d="M 136 214 Q 150 204 164 214 A 16 18 0 0 1 136 214 Z" fill="#5e3b4d" opacity="0.65" />
              </g>
              <g className="ghost-eye-left">
                <g className="ghost-eye-main">
                  <ellipse cx="112" cy="145" rx="23.5" ry="47.5" fill={`url(#${id}-eye-rim-grad)`} />
                  <ellipse cx="112" cy="145" rx="20.5" ry="44.5" fill={`url(#${id}-eye-fill-grad)`} />
                  <ellipse cx="112" cy="172" rx="14" ry="12" fill="#6f82a0" opacity="0.35" />
                  <g className="ghost-eye-shine">
                    <ellipse cx="104" cy="120" rx="7.5" ry="15.5" transform="rotate(21 104 120)" fill="#ffffff" />
                    <circle cx="122.5" cy="144" r="4.2" fill="#ffffff" />
                  </g>
                </g>
                <path className="ghost-happy-arc" d="M 90 148 Q 112 115 134 148" fill="none" stroke="#101520" strokeWidth="8" strokeLinecap="round" />
              </g>
              <g className="ghost-eye-right">
                <g className="ghost-eye-main">
                  <ellipse cx="188" cy="145" rx="23.5" ry="47.5" fill={`url(#${id}-eye-rim-grad)`} />
                  <ellipse cx="188" cy="145" rx="20.5" ry="44.5" fill={`url(#${id}-eye-fill-grad)`} />
                  <ellipse cx="188" cy="172" rx="14" ry="12" fill="#6f82a0" opacity="0.35" />
                  <g className="ghost-eye-shine">
                    <ellipse cx="180" cy="120" rx="7.5" ry="15.5" transform="rotate(21 180 120)" fill="#ffffff" />
                    <circle cx="198.5" cy="144" r="4.2" fill="#ffffff" />
                  </g>
                </g>
                <path className="ghost-happy-arc" d="M 166 148 Q 188 115 210 148" fill="none" stroke="#101520" strokeWidth="8" strokeLinecap="round" />
              </g>
            </g>
          </g>
        </g>
        <path d="M 46 112 C 60 66, 98 38, 132 34 C 118 48, 78 78, 58 118 C 52 128, 42 124, 46 112 Z"
              fill="#ffffff" opacity="0.85" pointerEvents="none" />
      </svg>);
}
