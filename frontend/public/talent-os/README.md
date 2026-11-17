# IT Talent AI OS V7 — Arctic Intelligence

New **Arctic Intelligence / Editorial Tech** light mode: cool off-white canvas, ink typography, cobalt and teal accents, white cards, clear borders, accessible contrast. Existing dark mode and interactions retained.

## Preview

From this directory:

```bash
python -m http.server 5500
```

Open http://localhost:5500/ for the About Me landing, then Launch Workspace. Switch themes using the theme toggle. Clicking the brand from workspace pages returns to index.html.

This is a standalone visual prototype with illustrative data, not an authenticated GitHub or AI integration. Three.js scenes require Internet access for external dependencies.


## V8 — Immersive ambient 3D
- Landing page `index.html`: 5 mô hình wireframe Three.js chìm trong background, hạt nền, parallax theo chuột/cuộn trang.
- Hero 3D: kéo xoay, Change form (3 hình dạng), Pause/Resume motion.
- Hình quỹ đạo và họa tiết hình học tại các section; cursor glow chỉ trên thiết bị có chuột.
- Canvas background `pointer-events:none`, không chặn thao tác; tự thay màu theo Dark/Light; tôn trọng reduced-motion.
- Cần Internet để tải Three.js từ CDN. Đây là demo, không tích hợp backend.


## V9 — Code streams background
About Me (`index.html`) replaces the V8 background wireframe objects with decorative scrolling code in Python, TypeScript, JavaScript, Rust, Go, Java, C#, SQL, HTML, CSS, Kotlin, and Swift. Snippets are illustrative and never executed. The hero 3D scene and all other pages are preserved. Motion respects reduced-motion settings.
