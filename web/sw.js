// 一度開いたあとは、ネットにつながっていなくても動くように、ページが使うファイルをブラウザに
// 持っておく(Service Worker)。VERSIONとFILESはbuild.pyが入れる。FILESはこのページからの位置。
// ページが読むファイルは、中身が変われば名前も変わる(app.zip?ハッシュ、pyodide/版/)。そのため、
// 新しい版に入れ替わる途中でも、ページは自分の版のファイルだけを読む
const VERSION = "{{VERSION}}";
const FILES = {{FILES}};
const CACHE = `sc61box-${VERSION}`;

// 新しい版は、すべてのファイルを持てたときだけ入る(持てなければ、前の版のまま)。前の版で開いて
// いるページがあるあいだは、入れ替わらずに待つ(skipWaitingしない)
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)));
});

// 入れ替わったら(前の版のページはもうない)、前に持っていたものを捨てる
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys
    .filter((k) => k.startsWith("sc61box-") && k !== CACHE)
    .map((k) => caches.delete(k)))));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  if (req.mode === "navigate") {
    // ページは、つながれば新しいものを使う(新しい版のファイルはネットから読む)。つながらなければ、
    // この版で持っているものを使う(?model=などは見ない)
    e.respondWith(fetch(req).catch(() =>
      caches.open(CACHE).then((c) => c.match("./", { ignoreSearch: true }))));
    return;
  }
  e.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
});
