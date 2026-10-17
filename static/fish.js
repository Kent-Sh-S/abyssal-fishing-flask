/* Original vector specimens. No downloaded art or third-party assets. */
(() => {
  let serial = 0;
  window.fishArt = (fish, options = {}) => {
    const id = `specimen-${++serial}`;
    const color = fish.color || '#aec694';
    const kind = fish.kind || 'angler';
    const eye = (x, y, r = 10) => `<circle cx="${x}" cy="${y}" r="${r + 3}" fill="#111f19"/><circle cx="${x}" cy="${y}" r="${r}" fill="${color}"/><circle cx="${x + 1}" cy="${y}" r="${r * .47}" fill="#13221c"/><circle cx="${x - 2}" cy="${y - 3}" r="${r * .21}" fill="#f1f2ca"/>`;
    const ribs = Array.from({length: 11}, (_, i) => `<path d="M${107 + i * 13} 112q${12 + i * 1.3} 22 0 ${40 + Math.sin(i) * 13}"/>`).join('');
    const scales = Array.from({length: 48}, (_, i) => {
      const x = 112 + (i % 8) * 19 + Math.sin(i * 3) * 4;
      const y = 91 + Math.floor(i / 8) * 12 + Math.cos(i) * 5;
      return `<path d="M${x} ${y}q7 6 12-1" opacity="${.08 + (i % 4) * .025}"/>`;
    }).join('');
    const fins = `<path d="M134 87 141 42l18 23 15-38 17 33 21-31 8 36 30-19-7 41" fill="url(#${id}-fin)" stroke="${color}" stroke-opacity=".28"/><g stroke="${color}" stroke-opacity=".25" stroke-width=".8"><path d="m142 48 10 42m22-53 2 51m34-48-10 45m30-29-15 33"/></g><path d="m166 166 5 44 20-16 17 15 20-45" fill="url(#${id}-fin)" stroke="${color}" stroke-opacity=".25"/><g stroke="${color}" stroke-width=".8" opacity=".22"><path d="m176 177 1 25m14-23-1 17m10-19 5 25m7-28 2 17"/></g>`;
    const tail = `<path d="M108 115C80 107 64 79 35 76l12 26-19 6 24 16-20 21 17 2-14 31c36-7 48-37 72-39Z" fill="url(#${id}-fin)" stroke="${color}" stroke-opacity=".3"/><g fill="none" stroke="${color}" stroke-opacity=".2" stroke-width=".8"><path d="M43 84q30 28 64 40M38 110l64 16M42 144l63-16M42 169q30-29 63-39"/></g>`;
    let art = '';
    if (kind === 'angler' || kind === 'eyes' || kind === 'skeleton') {
      art = `${tail}${fins}<path d="M91 119C112 70 172 61 226 74c35 1 64 12 85 36l-18 14 31 28c-26 38-91 47-144 28-45-3-72-22-89-43Z" fill="url(#${id}-body)" stroke="${color}" stroke-opacity=".45" stroke-width="1.1"/><path d="M103 131c50 26 126 20 194-8-9 35-64 55-117 44-32-3-54-16-77-36Z" fill="#0a1716" opacity=".35"/><g fill="none" stroke="${color}" stroke-width="1.1">${scales}</g><path d="M236 93q-25 31 4 63M242 91q-23 37 7 63" fill="none" stroke="#12251b" stroke-opacity=".65" stroke-width="2"/><path d="M213 124c-4 0-29 16-30 48 28-12 41-23 48-34Z" fill="url(#${id}-fin)" stroke="${color}" stroke-opacity=".3"/><g stroke="${color}" stroke-width=".6" opacity=".3"><path d="m215 133-28 33m30-30-17 22m20-18-11 9"/></g>`;
      if (kind === 'angler') {
        const teeth = Array.from({length: 7}, (_, i) => `<path d="m${278 + i * 6} ${112 + i * 2.1} 2 15 4-13" fill="#ced6ab" opacity="${.55 + i * .04}"/>`).join('');
        art += `<path d="M276 110q34 4 53 31-28-3-43 9l-11-15Z" fill="#07120f"/><path d="M281 112q29 6 46 28M285 151l42-11" fill="none" stroke="${color}" stroke-opacity=".6" stroke-width="2"/>${teeth}<path d="m296 148 4-13 4 11m5-1 3-9 3 8" fill="#cbd6ac" opacity=".7"/>${eye(266, 99, 12)}<path d="M234 78c-21-23-10-62 27-57 25 3 31 21 28 37" fill="none" stroke="${color}" stroke-opacity=".65" stroke-width="2"/><circle cx="289" cy="61" r="25" fill="url(#${id}-glow)"/><ellipse cx="289" cy="61" rx="5" ry="7" fill="#dce7b5"/><ellipse cx="288" cy="59" rx="2" ry="3" fill="#f1f4d2"/>`;
      } else if (kind === 'eyes') {
        art += `${eye(275, 103, 13)}${eye(240, 97, 10)}${eye(209, 103, 12)}${eye(179, 96, 8)}${eye(151, 112, 9)}${eye(188, 133, 11)}${eye(224, 135, 9)}${eye(261, 137, 8)}<path d="m294 126 18 7-18 6" fill="#131a1b" stroke="${color}" stroke-opacity=".5"/>`;
      } else {
        art += `<g fill="none" stroke="${color}" stroke-width="2" opacity=".7"><path d="M95 126q95-12 195 1"/>${ribs}<path d="m268 93 21 9-6 14-21 3-7-16Z"/></g><path d="M269 123q18 16 37 18l-13 13-28-11Z" fill="#273e36" stroke="${color}" stroke-opacity=".4"/>${eye(276, 103, 7)}`;
      }
    } else if (kind === 'jelly') {
      const tendrils = Array.from({length: 9}, (_, i) => `<path d="M${145 + i * 14} 110c${-50 + i * 11} 35 ${55 - i * 8} 57 ${-27 + i * 4} 88s${30 - i * 4} 21 ${-6 + i} 28" fill="none" stroke="${color}" stroke-width="${i % 3 === 0 ? 3 : 1}" opacity="${.25 + (i % 4) * .12}"/>`).join('');
      art = `<ellipse cx="201" cy="99" rx="83" ry="46" fill="url(#${id}-glow)"/>${tendrils}<path d="M129 106c0-98 140-98 144 0-17 16-32 19-44 4-12 17-24 17-34 0-13 15-25 15-34-1-14 13-26 14-32-3Z" fill="url(#${id}-body)" stroke="${color}" stroke-opacity=".65"/><g fill="none" stroke="${color}" stroke-opacity=".2"><path d="M199 40q-45 19-38 69M199 40q42 23 30 71M199 40l-3 70"/></g><path d="M169 80q30-32 61 0-10 28-30 20-19 8-31-20Z" fill="${color}" opacity=".22"/>${eye(184, 85, 5)}${eye(212, 85, 5)}`;
    } else if (kind === 'eel') {
      art = `<path d="M327 92c-45-49-94 0-127 41-24 30-46 46-73 32-38-20-50-67-84-79 39 1 61 22 73 38 29 31 41-12 67-42 47-56 107-58 144-13Z" fill="url(#${id}-body)" stroke="${color}" stroke-opacity=".6"/><path d="M42 86c46-20 66 16 97 25 17-5 29-28 42-42 65-57 132-43 155 14-38-52-96-48-148 13-28 32-47 60-72 28C95 95 77 87 42 86Z" fill="url(#${id}-fin)" opacity=".5"/><path d="M305 79q13 13 29 13l-18 13-25-6" fill="#0e1b16" stroke="${color}" stroke-opacity=".6"/><path d="m302 82 4 15m4-12 5 13m4-11 5 10m3-8 5 6" stroke="${color}" stroke-width="1.5"/>${eye(306, 67, 8)}<path d="M123 145q30 15 59-32M198 93q36-44 65-43" fill="none" stroke="${color}" stroke-opacity=".3"/>`;
    } else if (kind === 'ray') {
      art = `<path d="M205 51c-55 22-82 70-173 70 62 69 124 46 171 13 44 36 109 53 170-11-90-4-120-48-168-72Z" fill="url(#${id}-body)" stroke="${color}" stroke-opacity=".6"/><path d="M202 131c-16 52 28 63 18 99" fill="none" stroke="${color}" stroke-width="3" stroke-opacity=".7"/><path d="M206 56c-21 22-29 54-3 78 18-29 19-48 3-78Z" fill="${color}" opacity=".2"/><g fill="none" stroke="${color}" opacity=".2"><path d="m60 132 112-25m-91 42 89-31m174 13-106-22m82 43-80-33"/></g>${eye(190, 90, 5)}${eye(214, 90, 5)}<circle cx="202" cy="112" r="4" fill="#e6d7e7" opacity=".6"/>`;
    } else {
      const arms = Array.from({length: 9}, (_, i) => {
        const angle = i / 9 * Math.PI * 2;
        const x = 200 + Math.cos(angle) * 65, y = 116 + Math.sin(angle) * 45;
        const ex = 200 + Math.cos(angle + .5) * 153, ey = 116 + Math.sin(angle + .5) * 99;
        return `<path d="M${x} ${y}q${Math.cos(angle - 1) * 85} ${Math.sin(angle - 1) * 80} ${ex - x} ${ey - y}" stroke="${color}" stroke-width="${kind === 'ancient' ? 7 : 4}" stroke-linecap="round" fill="none" opacity=".35"/>`;
      }).join('');
      art = `${arms}<path d="M142 91q15-42 65-32 54-12 66 43 23 46-34 66-48 32-86-9-33-21-11-68Z" fill="url(#${id}-body)" stroke="${color}" stroke-opacity=".4"/><ellipse cx="207" cy="116" rx="53" ry="31" fill="#0a1611" stroke="${color}" stroke-opacity=".55"/><ellipse cx="207" cy="116" rx="29" ry="25" fill="${color}" opacity=".7"/><ellipse cx="207" cy="116" rx="7" ry="23" fill="#111c14"/><circle cx="197" cy="105" r="5" fill="#e5e7bc" opacity=".6"/>`;
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 240" role="img" aria-label="${fish.name}"><defs><linearGradient id="${id}-body" x1=".25" y1="0" x2=".65" y2="1"><stop stop-color="${color}" stop-opacity=".75"/><stop offset=".37" stop-color="${color}" stop-opacity=".45"/><stop offset="1" stop-color="#192b21"/></linearGradient><linearGradient id="${id}-fin" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${color}" stop-opacity=".14"/><stop offset=".6" stop-color="${color}" stop-opacity=".45"/><stop offset="1" stop-color="#1c3528" stop-opacity=".5"/></linearGradient><radialGradient id="${id}-glow"><stop stop-color="${color}" stop-opacity=".35"/><stop offset=".4" stop-color="${color}" stop-opacity=".12"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></radialGradient></defs><g>${art}</g></svg>`;
  };
})();
