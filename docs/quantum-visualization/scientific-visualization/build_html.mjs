// Build the local SOP with an already installed marked module; never install packages.
import { readFile, writeFile, stat } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const directory = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
if (args.length && !(args.length === 2 && args[0] === '--marked')) {
  throw new Error('Usage: node build_html.mjs [--marked /local/path/marked.esm.js]');
}
const { marked } = await import(args.length ? pathToFileURL(resolve(args[1])).href : 'marked');
const markdown = await readFile(resolve(directory, 'README.md'), 'utf8');
const toc = markdown.match(/<!-- TOC START -->([\s\S]*?)<!-- TOC END -->/);
if (!toc) throw new Error('Explicit table of contents is missing');
const body = marked.parse(markdown.replace(toc[0], ''));
const navigation = marked.parse(toc[1]);
const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>ChemBlender · 科学量可视化操作手册</title>
<style>
:root{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#203348;background:#eef2f6;line-height:1.8;font-size:16px;scroll-behavior:smooth}
*{box-sizing:border-box}body{margin:0}header{background:#153049;color:#eef7ff;padding:22px max(24px,calc((100vw - 1460px)/2));border-bottom:4px solid #24b6a6}header strong{font-size:21px;letter-spacing:.05em}header span{display:block;color:#bdd3e5;font-size:14px}
.layout{display:grid;grid-template-columns:290px minmax(0,1fr);gap:28px;max-width:1460px;margin:0 auto;padding:28px 24px}nav{position:sticky;top:20px;align-self:start;max-height:calc(100vh - 40px);overflow:auto;background:#fff;border:1px solid #dbe4eb;border-radius:12px;padding:20px;font-size:14px}nav ul{list-style:none;padding:0;margin:12px 0 0}nav li{margin:8px 0}nav a{text-decoration:none}article{min-width:0;background:white;border:1px solid #dbe4eb;border-radius:12px;padding:38px 44px}h1{font-size:32px;line-height:1.35;color:#153049;margin:0 0 24px}h2{font-size:23px;color:#173d5b;border-top:1px solid #dce6ee;padding-top:32px;margin-top:38px}a{color:#006f91;text-underline-offset:3px}a:hover{color:#005040}a[id]{scroll-margin-top:24px}p,ul,ol{margin:14px 0}li{margin:7px 0}strong{color:#153b54}header strong{color:inherit}code{font-family:Consolas,"Cascadia Code",monospace;font-size:.9em;background:#edf3f7;border-radius:4px;padding:2px 5px;overflow-wrap:anywhere}pre{background:#132c42;color:#eaf3fb;border-radius:8px;padding:18px;overflow:auto;line-height:1.65}pre code{background:none;padding:0;color:inherit;overflow-wrap:normal}table{display:block;overflow:auto;border-collapse:collapse;width:100%;font-size:14px;margin:22px 0}th,td{text-align:left;vertical-align:top;border:1px solid #d9e4eb;padding:10px 12px;min-width:125px}th{background:#eaf3f7;color:#153b54}tr:nth-child(even){background:#f8fafc}img{display:block;max-width:100%;height:auto;border-radius:7px;margin:22px auto}blockquote{margin:22px 0;border-left:4px solid #24b6a6;background:#f0f8f7;padding:5px 20px}footer{padding:10px 24px 30px;text-align:center;color:#5c7082;font-size:13px}
@media(max-width:980px){.layout{grid-template-columns:1fr;padding:16px;gap:16px}nav{position:static;max-height:none}nav ul{columns:2}article{padding:26px}h1{font-size:28px}}
@media(max-width:560px){nav ul{columns:1}article{padding:20px 16px}h1{font-size:25px}h2{font-size:21px}th,td{min-width:145px}}
@media print{body{background:white}.layout{display:block;padding:0}nav,header,footer{display:none}article{border:0;padding:0}table{display:table;font-size:10pt}pre{white-space:pre-wrap}a{color:inherit}h2{break-after:avoid}img,pre{break-inside:avoid}}
</style></head><body>
<header><strong>CHEMBLENDER / SCIENTIFIC VISUALIZATION</strong><span>真实输入 · 科学语义 · 公开面板 · 可重放出图</span></header>
<div class="layout"><nav aria-label="章节目录"><strong>操作目录</strong>${navigation}</nav><article>${body}</article></div>
<footer>离线工作稿 · 科学完成状态以手册中的验证表及实际来源报告为准。</footer></body></html>`;

const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
if (new Set(ids).size !== ids.length) throw new Error('Duplicate HTML anchors');
let checked = 0;
for (const match of html.matchAll(/\b(href|src)="([^"]*)"/g)) {
  const [, kind, encoded] = match;
  const target = encoded.replaceAll('&amp;', '&');
  if (!target) throw new Error('Empty resource or link');
  if (/^https?:\/\//.test(target)) {
    if (kind === 'src') throw new Error('Offline HTML cannot load remote resources');
    continue;
  }
  if (/^[a-z][a-z0-9+.-]*:/i.test(target) || target.startsWith('//')) throw new Error(`Unsupported link: ${target}`);
  const [local, anchor] = target.split('#');
  if (!local) {
    if (!ids.includes(decodeURIComponent(anchor))) throw new Error(`Missing anchor: ${target}`);
  } else {
    const path = resolve(directory, decodeURIComponent(local));
    // The HTML self-link becomes valid when this build is published.
    if (path !== resolve(directory, 'index.html')) await stat(path);
    if (anchor) {
      const linked = await readFile(path, 'utf8');
      if (!linked.includes(`id="${decodeURIComponent(anchor)}"`)) throw new Error(`Missing linked anchor: ${target}`);
    }
  }
  checked++;
}
if (/<script\b/i.test(html)) throw new Error('Unexpected executable script in offline SOP');
await writeFile(resolve(directory, 'index.html'), html.replace(/\r?\n/g, '\r\n'), 'utf8');
console.log(`Built index.html: ${ids.length} anchors, ${checked} checked local links, no remote resources`);
